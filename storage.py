"""SQLite persistence for documents and generation jobs."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from document_pipeline import DocumentBlock, ProcessedDocument


class StudioStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._lock = threading.Lock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, source_name TEXT NOT NULL, parser TEXT NOT NULL,
                    blocks_json TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                    meta_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, job_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS listening_history (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                    source_name TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
                    block_idx INTEGER NOT NULL, snippet TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(documents)")}
            for column in ("display_name", "description", "meta_json"):
                if column not in columns:
                    default = "'{}'" if column == "meta_json" else "''"
                    connection.execute(f"ALTER TABLE documents ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_document(self, document_id: str, document: ProcessedDocument) -> None:
        now = self._timestamp()
        payload = json.dumps([asdict(block) for block in document.blocks], ensure_ascii=False)
        meta_json = json.dumps(document.meta or {}, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT INTO documents (id, source_name, parser, blocks_json, created_at, updated_at,
                                       display_name, description, meta_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET source_name=excluded.source_name,
                    parser=excluded.parser, blocks_json=excluded.blocks_json, updated_at=excluded.updated_at,
                    display_name=excluded.display_name, description=excluded.description, meta_json=excluded.meta_json
            """, (document_id, document.source_name, document.parser, payload, now, now,
                  document.display_name, document.description, meta_json))

    @staticmethod
    def _row_metadata(row: sqlite3.Row) -> dict:
        try:
            meta = json.loads(row["meta_json"]) if row["meta_json"] else {}
        except (ValueError, KeyError):
            meta = {}
        return {"display_name": row["display_name"] or "", "description": row["description"] or "", "meta": meta if isinstance(meta, dict) else {}}

    def get_document(self, document_id: str) -> ProcessedDocument | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if row is None:
            return None
        blocks = [DocumentBlock(**block) for block in json.loads(row["blocks_json"])]
        info = self._row_metadata(row)
        return ProcessedDocument(source_name=row["source_name"], parser=row["parser"], blocks=blocks, **info)

    def list_documents(self, limit: int = 100) -> list[dict[str, str | int]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, source_name, parser, blocks_json, created_at, updated_at, "
                "display_name, description, meta_json "
                "FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,),
            ).fetchall()
        documents: list[dict[str, str | int]] = []
        for row in rows:
            entry: dict[str, str | int] = {
                "id": row["id"], "source_name": row["source_name"], "parser": row["parser"],
                "block_count": len(json.loads(row["blocks_json"])), "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            entry.update(self._row_metadata(row))
            documents.append(entry)
        return documents

    def update_document_metadata(
        self,
        document_id: str,
        display_name: str,
        description: str,
        meta: dict | None,
    ) -> bool:
        now = self._timestamp()
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "UPDATE documents SET display_name = ?, description = ?, meta_json = ?, updated_at = ? "
                "WHERE id = ?",
                (display_name, description, meta_json, now, document_id),
            )
            return cursor.rowcount > 0

    def delete_document(self, document_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            connection.execute("DELETE FROM listening_history WHERE document_id = ?", (document_id,))
            return cursor.rowcount > 0

    def record_listening(self, entry: dict) -> None:
        """Upsert one listened block; the PK is document:idx so replays just refresh the timestamp."""
        now = self._timestamp()
        history_id = f"{entry['document_id']}:{entry['block_idx']}"
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT INTO listening_history (id, document_id, source_name, display_name, block_idx, snippet, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET created_at=excluded.created_at, snippet=excluded.snippet,
                    display_name=excluded.display_name, source_name=excluded.source_name
            """, (history_id, entry["document_id"], entry.get("source_name", ""),
                  entry.get("display_name", ""), entry["block_idx"], entry.get("snippet", ""), now))

    def list_listening(self, limit: int = 60) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT document_id, source_name, display_name, block_idx, snippet, created_at "
                "FROM listening_history ORDER BY created_at DESC LIMIT ?", (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_listening(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM listening_history")

    def save_job(self, job: dict) -> None:
        now = self._timestamp()
        with self._lock, self._connect() as connection:
            connection.execute("""
                INSERT INTO jobs (id, job_json, created_at, updated_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET job_json=excluded.job_json, updated_at=excluded.updated_at
            """, (job["id"], json.dumps(job, ensure_ascii=False), now, now))

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT job_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return json.loads(row["job_json"]) if row else None

    def list_jobs(self, limit: int) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute("SELECT job_json FROM jobs ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row["job_json"]) for row in rows]

    def delete_job(self, job_id: str) -> bool:
        with self._lock, self._connect() as connection:
            result = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return result.rowcount > 0
