# DocuSync AI

A compact local PDF RAG application with a FastAPI API, Streamlit UI, SQLite account catalog, persistent ChromaDB vectors, Google embeddings, and Gemini responses.

## Setup

Use Python 3.10 on Windows for the pinned ChromaDB release (Python 3.12 may require Microsoft C++ Build Tools to compile Chroma's HNSW dependency). From this folder:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`: set `GOOGLE_API_KEY` and generate a private `JWT_SECRET` with at least 32 characters (for example, `python -c "import secrets; print(secrets.token_urlsafe(48))"`). Keep `.env` out of source control. The API initializes `db/users.db` and local Chroma storage on startup.

Start the API and UI in separate terminals:

```powershell
uvicorn app:app --host 127.0.0.1 --port 8000
```

```powershell
streamlit run ui.py
```

Open the Streamlit URL printed in the terminal. `/docs` exposes interactive API documentation. For development, binding to `127.0.0.1` keeps the service local.

## Notes

- Each user has a distinct Chroma collection, plus user and document metadata filters on retrieval and deletion. API authorization derives user identity from the verified JWT; clients cannot select another user ID.
- Uploads are size-limited, saved beneath a UUID-named user folder, and accepted only when the PDF signature matches. Text extraction is performed with pypdf; image-only scans need OCR before upload.
- Gemini embeddings and generation require network access and may incur provider charges. SQLite, Chroma, and uploads are local. Local disk storage is a single-host development/small deployment setup; use managed storage, backups, rate limiting, TLS, and an operational secret manager before exposing it publicly.
- Passwords are hashed with bcrypt. Use a unique 32+ character `JWT_SECRET`; changing it invalidates existing access tokens.
- Tunable chunking, retrieval count, upload cap, paths, API URL, and model names are environment variables; see `.env.example`.
