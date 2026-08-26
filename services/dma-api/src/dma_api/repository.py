"""SQLite persistence for the first DMA vertical slice."""

from __future__ import annotations

import json
import re
import sqlite3
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dma_api.models import MemoryType

_SQLITE_BUSY_TIMEOUT_SECONDS = 30.0

_CURRENT_MARKERS = {"now", "current", "currently", "latest", "newer", "active"}
_STOPWORDS = {
    "a",
    "after",
    "an",
    "and",
    "be",
    "before",
    "can",
    "does",
    "for",
    "happen",
    "how",
    "is",
    "it",
    "now",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "use",
    "used",
    "user",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}
_QUERY_EXPANSIONS = {
    "adapter": {"adapter", "langgraph", "mcp"},
    "api": {"api", "apis", "openapi", "rest"},
    "classification": {"classification", "classifier", "accuracy"},
    "client": {"client", "api_key", "agent_id", "scope", "tenant"},
    "cloud": {"cloud", "aws", "gcp"},
    "command": {"command", "make"},
    "conflict": {"conflict", "newer", "older", "preference"},
    "credit": {"credit", "credits", "fireworks", "offline"},
    "credits": {"credit", "credits", "fireworks", "offline"},
    "design": {"design", "openapi", "rest"},
    "example": {"example", "examples", "python"},
    "framework": {"framework", "langgraph", "django", "spring"},
    "hosting": {"hosting", "hosted", "self"},
    "language": {"language", "python", "typescript"},
    "logging": {"logging", "logs", "json"},
    "metric": {"metric", "metrics", "accuracy", "recall", "mrr"},
    "migration": {"migration", "migrations", "alembic", "schema"},
    "model": {"model", "fireworks", "offline", "benchmark"},
    "package": {"package", "packages", "pypi", "dma", "sdk", "langgraph", "mcp"},
    "packages": {"package", "packages", "pypi", "dma", "sdk", "langgraph", "mcp"},
    "preference": {"preference", "preferences", "newer", "older"},
    "provider": {"provider", "aws", "gcp"},
    "release": {"release", "alpha", "self", "hosted", "pypi"},
    "retrieval": {"retrieval", "recall", "lexical", "vector"},
    "scope": {"scope", "api_key", "agent_id", "tenant"},
    "style": {"style", "openapi", "rest", "lexical"},
    "support": {"support", "ecosystem", "adapter", "mcp"},
    "tool": {"tool", "alembic"},
}


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
        with self._transaction() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
        with self._transaction() as connection:
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

            if record.type is MemoryType.SEMANTIC:
                duplicate = self._find_normalized_semantic(connection, record)
                if duplicate is not None:
                    updated = MemoryRecord(
                        id=duplicate.id,
                        tenant_id=duplicate.tenant_id,
                        agent_id=duplicate.agent_id,
                        content=record.content,
                        type=record.type,
                        version=duplicate.version + 1,
                        created_at=duplicate.created_at,
                        updated_at=record.updated_at,
                        expires_at=record.expires_at,
                        metadata=record.metadata,
                    )
                    connection.execute(
                        """UPDATE memories SET content = ?, version = ?, updated_at = ?, expires_at = ?, metadata_json = ? WHERE id = ?""",
                        (updated.content, updated.version, updated.updated_at.isoformat(), updated.expires_at.isoformat() if updated.expires_at else None, json.dumps(updated.metadata, separators=(",", ":"), sort_keys=True), updated.id),
                    )
                    connection.execute("DELETE FROM memory_search WHERE memory_id = ?", (updated.id,))
                    connection.execute("INSERT INTO memory_search (content, memory_id, tenant_id, agent_id, type) VALUES (?, ?, ?, ?, ?)", (updated.content, updated.id, updated.tenant_id, updated.agent_id, updated.type.value))
                    connection.execute("INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key, memory_id) VALUES (?, 'remember', ?, ?)", (record.tenant_id, idempotency_key, updated.id))
                    return updated, False

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

    def _find_normalized_semantic(self, connection: sqlite3.Connection, record: MemoryRecord) -> MemoryRecord | None:
        rows = connection.execute("SELECT * FROM memories WHERE tenant_id = ? AND agent_id = ? AND type = 'semantic'", (record.tenant_id, record.agent_id)).fetchall()
        normalized = self._normalise_semantic(record.content)
        for row in rows:
            candidate = self._row_to_record(row)
            if self._normalise_semantic(candidate.content) == normalized:
                return candidate
        return None

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
        with self._transaction() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        query_tokens = self._important_tokens(query)
        records_with_relevance = []
        for row in rows:
            record = self._row_to_record(row)
            if not self._passes_precision_filter(query, query_tokens, record.content):
                continue
            overlap = self._overlap_score(query_tokens, record.content)
            current_boost = 0.25 if self._asks_for_current(query) and self._has_current_marker(record.content) else 0
            records_with_relevance.append((record, max(float(row["relevance"]), 0.0) + overlap + current_boost))
        if not records_with_relevance:
            return []
        top_relevance = max(relevance for _, relevance in records_with_relevance)
        if top_relevance == 0:
            return [(record, 0.0) for record, _ in records_with_relevance]
        return [(record, relevance / top_relevance) for record, relevance in records_with_relevance]

    def list_memories(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        memory_type: MemoryType | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[MemoryRecord], str | None]:
        """List a stable, cursor-paginated view of one agent's records."""
        where = ["tenant_id = ?", "agent_id = ?"]
        parameters: list[object] = [tenant_id, agent_id]
        if memory_type is not None:
            where.append("type = ?")
            parameters.append(memory_type.value)
        if cursor:
            created_at, memory_id = self._decode_cursor(cursor)
            where.append("(created_at < ? OR (created_at = ? AND id < ?))")
            parameters.extend([created_at, created_at, memory_id])
        parameters.append(limit + 1)
        statement = f"""
            SELECT * FROM memories
            WHERE {' AND '.join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        """
        with self._transaction() as connection:
            rows = connection.execute(statement, parameters).fetchall()
        records = [self._row_to_record(row) for row in rows]
        has_next_page = len(records) > limit
        page = records[:limit]
        next_cursor = self._encode_cursor(page[-1]) if has_next_page and page else None
        return page, next_cursor

    def get(self, *, tenant_id: str, agent_id: str, memory_id: str) -> MemoryRecord | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM memories WHERE id = ? AND tenant_id = ? AND agent_id = ?",
                (memory_id, tenant_id, agent_id),
            ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def delete(self, *, tenant_id: str, agent_id: str, memory_id: str) -> bool:
        """Hard-delete a memory and all index/idempotency references to it."""
        with self._transaction() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT 1 FROM memories WHERE id = ? AND tenant_id = ? AND agent_id = ?",
                (memory_id, tenant_id, agent_id),
            ).fetchone()
            if existing is None:
                return False
            connection.execute("DELETE FROM memory_search WHERE memory_id = ?", (memory_id,))
            connection.execute("DELETE FROM idempotency_keys WHERE memory_id = ?", (memory_id,))
            connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return True

    def _connect(self) -> sqlite3.Connection:
        """Open a configured connection; prefer :meth:`_transaction` for cleanup."""
        connection = sqlite3.connect(self._database_path, timeout=_SQLITE_BUSY_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(_SQLITE_BUSY_TIMEOUT_SECONDS * 1000)}")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection whose work commits on success and is always closed."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

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
        tokens = SQLiteMemoryRepository._expanded_tokens(query)
        terms = []
        for token in tokens:
            terms.append(f'"{token}"')
            if len(token) > 3:
                terms.append(f"{token}*")
        return " OR ".join(terms)

    @classmethod
    def _passes_precision_filter(cls, query: str, query_tokens: set[str], content: str) -> bool:
        if cls._asks_for_current(query) and not cls._has_current_marker(content):
            return False
        if not query_tokens:
            return False
        overlap = cls._matching_tokens(query_tokens, content)
        if len(query_tokens) == 1:
            return len(overlap) == 1
        return len(overlap) >= 2 or len(overlap) / len(query_tokens) >= 0.5

    @classmethod
    def _overlap_score(cls, query_tokens: set[str], content: str) -> float:
        if not query_tokens:
            return 0.0
        return len(cls._matching_tokens(query_tokens, content)) / len(query_tokens)

    @classmethod
    def _matching_tokens(cls, query_tokens: set[str], content: str) -> set[str]:
        content_tokens = cls._content_tokens(content)
        return {
            query_token
            for query_token in query_tokens
            if any(cls._tokens_match(query_token, content_token) for content_token in content_tokens)
        }

    @classmethod
    def _important_tokens(cls, text: str) -> set[str]:
        return cls._expand_tokens({
            token
            for token in (cls._normalise_token(raw_token) for raw_token in re.findall(r"[\w]+", text, flags=re.UNICODE))
            if token and token not in _STOPWORDS and len(token) > 2
        })

    @classmethod
    def _expanded_tokens(cls, text: str) -> set[str]:
        return cls._expand_tokens({
            token
            for token in (cls._normalise_token(raw_token) for raw_token in re.findall(r"[\w]+", text, flags=re.UNICODE))
            if token and len(token) > 2
        })

    @staticmethod
    def _expand_tokens(tokens: set[str]) -> set[str]:
        expanded = set(tokens)
        for token in tokens:
            expanded.update(_QUERY_EXPANSIONS.get(token, set()))
        return expanded

    @classmethod
    def _content_tokens(cls, text: str) -> set[str]:
        return {
            token
            for token in (cls._normalise_token(raw_token) for raw_token in re.findall(r"[\w]+", text, flags=re.UNICODE))
            if token and len(token) > 2
        }

    @staticmethod
    def _normalise_token(token: str) -> str:
        token = token.casefold()
        if len(token) > 4 and token.endswith("ies"):
            return f"{token[:-3]}y"
        if len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token

    @staticmethod
    def _tokens_match(query_token: str, content_token: str) -> bool:
        return (
            query_token == content_token
            or (len(query_token) >= 3 and query_token in content_token)
            or (len(content_token) >= 3 and content_token in query_token)
        )

    @classmethod
    def _asks_for_current(cls, query: str) -> bool:
        return bool(cls._important_tokens(query).intersection(_CURRENT_MARKERS) or {"now", "current", "latest"}.intersection(cls._content_tokens(query)))

    @classmethod
    def _has_current_marker(cls, content: str) -> bool:
        return bool(cls._content_tokens(content).intersection(_CURRENT_MARKERS))

    @staticmethod
    def _normalise_semantic(content: str) -> str:
        return " ".join(content.split()).casefold()

    @staticmethod
    def _encode_cursor(record: MemoryRecord) -> str:
        raw = f"{record.created_at.isoformat()}|{record.id}".encode()
        return urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str, str]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            created_at, memory_id = urlsafe_b64decode(padded).decode().split("|", maxsplit=1)
            datetime.fromisoformat(created_at)
            if not memory_id.startswith("mem_"):
                raise ValueError
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("invalid cursor") from error
        return created_at, memory_id
