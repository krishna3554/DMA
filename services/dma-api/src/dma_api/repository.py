"""SQLite persistence for the first DMA vertical slice."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dma_api.models import MemoryType


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    id: str
    tenant_id: str
    agent_id: str
    content: str
    type: MemoryType
    version: int
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    metadata: dict[str, object]


class SQLiteMemoryRepository:
    """A small persistence boundary that can later be replaced by PostgreSQL."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def initialize(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('episodic', 'semantic', 'procedural')),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT,
                    metadata_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_memories_scope
                    ON memories(tenant_id, agent_id, type, created_at DESC);
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5(
                    content,
                    memory_id UNINDEXED,
                    tenant_id UNINDEXED,
                    agent_id UNINDEXED,
                    type UNINDEXED,
                    tokenize = 'unicode61'
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    tenant_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    memory_id TEXT NOT NULL REFERENCES memories(id),
                    PRIMARY KEY (tenant_id, operation, idempotency_key)
                );
                """
            )

    def create_or_get(self, record: MemoryRecord, idempotency_key: str) -> tuple[MemoryRecord, bool]:
        """Create a record, or return the result of an exact idempotent replay."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT memory_id FROM idempotency_keys
                WHERE tenant_id = ? AND operation = 'remember' AND idempotency_key = ?
                """,
                (record.tenant_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                return self._get_by_id(connection, existing["memory_id"]), False

            connection.execute(
                """
                INSERT INTO memories (
                    id, tenant_id, agent_id, content, type, version,
                    created_at, updated_at, expires_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.tenant_id,
                    record.agent_id,
                    record.content,
                    record.type.value,
                    record.version,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.expires_at.isoformat() if record.expires_at else None,
                    json.dumps(record.metadata, separators=(",", ":"), sort_keys=True),
                ),
            )
            connection.execute(
                """
                INSERT INTO memory_search (content, memory_id, tenant_id, agent_id, type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (record.content, record.id, record.tenant_id, record.agent_id, record.type.value),
            )
            connection.execute(
                """
                INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key, memory_id)
                VALUES (?, 'remember', ?, ?)
                """,
                (record.tenant_id, idempotency_key, record.id),
            )
            return record, True

    def recall(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        query: str,
        types: list[MemoryType] | None,
        limit: int,
        now: datetime,
    ) -> list[tuple[MemoryRecord, float]]:
        """Return lexical matches visible to the agent, ordered by FTS relevance."""
        search_query = self._to_fts_query(query)
        if not search_query:
            return []

        where = [
            "memory_search MATCH ?",
            "m.tenant_id = ?",
            "m.agent_id = ?",
            "(m.expires_at IS NULL OR m.expires_at > ?)",
        ]
        parameters: list[object] = [search_query, tenant_id, agent_id, now.isoformat()]
        if types:
            placeholders = ", ".join("?" for _ in types)
            where.append(f"m.type IN ({placeholders})")
            parameters.extend(memory_type.value for memory_type in types)
        parameters.append(limit)

        statement = f"""
            SELECT m.*, -bm25(memory_search) AS relevance
            FROM memory_search
            JOIN memories AS m ON m.id = memory_search.memory_id
            WHERE {' AND '.join(where)}
            ORDER BY relevance DESC, m.created_at DESC
            LIMIT ?
        """
        with self._connect() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        return [(self._row_to_record(row), self._normalise_score(row["relevance"])) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _get_by_id(connection: sqlite3.Connection, memory_id: str) -> MemoryRecord:
        row = connection.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            raise RuntimeError("idempotency record references a missing memory")
        return SQLiteMemoryRepository._row_to_record(row)

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            agent_id=row["agent_id"],
            content=row["content"],
            type=MemoryType(row["type"]),
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def _to_fts_query(query: str) -> str:
        """Convert arbitrary user text to a safe OR query for SQLite FTS5.

        BM25 ranks records matching more query terms above partial matches. OR prevents
        a harmless wording variation (for example, ``prefer`` vs ``prefers``) from
        producing an empty result set before semantic retrieval is introduced.
        """
        tokens = re.findall(r"[\w]+", query, flags=re.UNICODE)
        return " OR ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def _normalise_score(relevance: float) -> float:
        """Map FTS5's unbounded BM25 value to a stable public 0..1 score."""
        positive_relevance = max(float(relevance), 0.0)
        return positive_relevance / (1.0 + positive_relevance)
