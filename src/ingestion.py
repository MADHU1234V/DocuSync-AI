"""PDF parsing, splitting, embedding, and isolated persistent Chroma storage."""

import hashlib
from pathlib import Path

import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from src.config import get_settings


def collection_name(user_id: str) -> str:
    # Hashing keeps names valid and prevents usernames or other PII appearing in Chroma.
    return "u_" + hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:40]


def _client():
    path = get_settings().chroma_path
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def _collection(user_id: str):
    # Each account gets a separate collection; user_id is also recorded on every item
    # and applied as a metadata filter as defense in depth.
    return _client().get_or_create_collection(
        name=collection_name(user_id), metadata={"hnsw:space": "cosine"}
    )


def _embedding_model():
    settings = get_settings()
    settings.validate_ai()
    return GoogleGenerativeAIEmbeddings(model=settings.embedding_model, google_api_key=settings.google_api_key)


def index_pdf(user_id: str, document_id: str, filename: str, pdf_path: Path) -> int:
    """Index one PDF and return the number of stored chunks."""
    reader = PdfReader(str(pdf_path))
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=get_settings().chunk_size,
        chunk_overlap=get_settings().chunk_overlap,
        add_start_index=True,
    )
    texts: list[str] = []
    metadatas: list[dict] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        for chunk in splitter.split_text(page_text):
            if chunk.strip():
                texts.append(chunk)
                metadatas.append({"user_id": user_id, "document_id": document_id,
                                  "filename": filename, "page": page_number})
    if not texts:
        raise ValueError("No extractable text found. Scanned PDFs need OCR before upload.")

    embeddings = _embedding_model().embed_documents(texts)
    collection = _collection(user_id)
    ids = [f"{document_id}_{i}" for i in range(len(texts))]
    # Batch requests modestly to avoid large transient memory use on an 8 GB laptop.
    for start in range(0, len(texts), 64):
        end = start + 64
        collection.upsert(ids=ids[start:end], documents=texts[start:end],
                          metadatas=metadatas[start:end], embeddings=embeddings[start:end])
    return len(texts)


def remove_document_vectors(user_id: str, document_id: str) -> None:
    collection = _collection(user_id)
    collection.delete(where={"$and": [{"user_id": user_id}, {"document_id": document_id}]})
