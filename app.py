"""FastAPI service for registration, document management, and grounded Q&A."""

import logging
import re
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from src.auth import create_access_token, get_current_user, hash_password, verify_password
from src.config import get_settings
from src.database import (add_document, create_user, delete_document_record, get_document,
                          get_user_by_username, init_db, list_documents, set_document_status)
from src.generator import answer_question
from src.ingestion import index_pdf, remove_document_vectors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("docusync")
app = FastAPI(title="DocuSync AI", version="1.0.0", description="Private, user-scoped PDF question answering")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=72)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


@app.on_event("startup")
def startup() -> None:
    get_settings().validate_auth()
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "ai_configured": bool(get_settings().google_api_key)}


def require_ai_configuration() -> None:
    try:
        get_settings().validate_ai()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict:
    # bcrypt accepts at most 72 bytes. Check bytes as Unicode characters may be multibyte.
    if len(payload.password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be at most 72 UTF-8 bytes for bcrypt")
    username = payload.username.strip()
    if not username:
        raise HTTPException(status_code=422, detail="Username cannot be blank")
    created = create_user(str(uuid4()), username, hash_password(payload.password))
    if not created:
        raise HTTPException(status_code=409, detail="Username is already registered")
    return {"message": "Account created. Log in to continue."}


@app.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends()) -> dict:
    user = get_user_by_username(form.username.strip())
    if not user or not verify_password(form.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    token, expires_in = create_access_token(user["id"], user["username"])
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in,
            "username": user["username"]}


@app.post("/upload-document", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
) -> dict:
    settings = get_settings()
    # Fail before saving an upload when the external AI provider is not configured.
    require_ai_configuration()
    raw_name = Path(file.filename or "document.pdf").name
    safe_name = re.sub(r"[^A-Za-z0-9._ -]", "_", raw_name).strip(" .")[:180] or "document.pdf"
    if not safe_name.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are accepted")
    document_id = str(uuid4())
    user_dir = settings.upload_path / current_user["id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    destination = user_dir / f"{document_id}.pdf"
    total = 0
    prefix = b""
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if not prefix:
                    prefix = chunk[:5]
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="PDF exceeds the configured upload limit")
                output.write(chunk)
        if prefix != b"%PDF-":
            raise HTTPException(status_code=415, detail="File content is not a valid PDF")

        add_document(document_id, current_user["id"], safe_name, str(destination))
        await run_in_threadpool(index_pdf, current_user["id"], document_id, safe_name, destination)
        return {"id": document_id, "filename": safe_name, "status": "ready"}
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except Exception as exc:
        logger.exception("PDF indexing failed for document %s", document_id)
        try:
            remove_document_vectors(current_user["id"], document_id)
            set_document_status(document_id, "failed")
        except Exception:
            pass
        destination.unlink(missing_ok=True)
        detail = str(exc) if isinstance(exc, ValueError) else "Document indexing failed. Check the PDF and AI service configuration."
        raise HTTPException(status_code=422, detail=detail) from exc
    finally:
        await file.close()


@app.get("/documents")
def documents(current_user: dict = Depends(get_current_user)) -> list[dict]:
    return list_documents(current_user["id"])


@app.delete("/documents/{document_id}")
def delete_document(document_id: str, current_user: dict = Depends(get_current_user)) -> dict:
    document = get_document(document_id, current_user["id"])
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        remove_document_vectors(current_user["id"], document_id)
    except Exception:
        logger.exception("Failed to remove indexed vectors for %s", document_id)
        raise HTTPException(status_code=500, detail="Could not remove document vectors")
    Path(document["stored_path"]).unlink(missing_ok=True)
    delete_document_record(document_id, current_user["id"])
    return {"message": "Document deleted"}


@app.post("/query")
def query(payload: QueryRequest, current_user: dict = Depends(get_current_user)) -> dict:
    require_ai_configuration()
    try:
        return answer_question(current_user["id"], payload.question.strip())
    except Exception as exc:
        logger.exception("Question answering failed for user %s", current_user["id"])
        raise HTTPException(status_code=503, detail="The AI service could not answer this request") from exc
