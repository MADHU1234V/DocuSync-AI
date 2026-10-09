"""Small SQLite account and document catalog for a single-host deployment."""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import get_settings


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    path: Path = get_settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ready',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS ix_documents_user ON documents(user_id, created_at);
            """
        )


def create_user(user_id: str, username: str, hashed_password: str) -> bool:
    try:
        with _connection() as conn:
            conn.execute("INSERT INTO users(id, username, hashed_password) VALUES (?, ?, ?)",
                         (user_id, username, hashed_password))
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_by_username(username: str):
    with _connection() as conn:
        row = conn.execute("SELECT id, username, hashed_password FROM users WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def add_document(document_id: str, user_id: str, filename: str, stored_path: str) -> None:
    with _connection() as conn:
        conn.execute("INSERT INTO documents(id, user_id, filename, stored_path) VALUES (?, ?, ?, ?)",
                     (document_id, user_id, filename, stored_path))


def list_documents(user_id: str) -> list[dict]:
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, filename, status, created_at FROM documents WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_document(document_id: str, user_id: str):
    with _connection() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)).fetchone()
        return dict(row) if row else None


def set_document_status(document_id: str, status: str) -> None:
    with _connection() as conn:
        conn.execute("UPDATE documents SET status = ? WHERE id = ?", (status, document_id))


def delete_document_record(document_id: str, user_id: str) -> bool:
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id))
        return cursor.rowcount == 1
