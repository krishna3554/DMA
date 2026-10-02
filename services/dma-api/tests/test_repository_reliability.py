from __future__ import annotations

import sqlite3
import threading

import pytest

from dma_api.models import MemoryType
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository


def _record(index: int) -> MemoryRecord:
    from datetime import UTC, datetime

    now = datetime(2026, 8, 27, tzinfo=UTC).replace(microsecond=index)
    return MemoryRecord(
        id=f"mem_{index:024x}",
        tenant_id="tenant-a",
        agent_id="coding-agent",
        content=f"Concurrent write test {index}.",
        type=MemoryType.EPISODIC,
        version=1,
        created_at=now,
        updated_at=now,
        expires_at=None,
        metadata={},
    )


def test_initialize_enables_wal_journal_mode(tmp_path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "dma.db")
    repository.initialize()

    with sqlite3.connect(tmp_path / "dma.db") as connection:
        mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert mode == "wal"


def test_connections_use_the_configured_busy_timeout(tmp_path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "dma.db")

    connection = repository._connect()
    try:
        timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        connection.close()

    assert timeout > 0


def test_transaction_closes_the_connection_after_use(tmp_path) -> None:
    repository = SQLiteMemoryRepository(tmp_path / "dma.db")
    repository.initialize()

    with repository._transaction() as connection:
        connection.execute(
            "INSERT INTO memories (id, tenant_id, agent_id, content, type, version,"
            " created_at, updated_at, expires_at, metadata_json)"
            " VALUES ('mem_x', 't', 'a', 'c', 'episodic', 1, '2026-01-01T00:00:00+00:00',"
            " '2026-01-01T00:00:00+00:00', NULL, '{}')"
        )

    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")  # connection is closed after the transaction block
    with sqlite3.connect(tmp_path / "dma.db") as fresh:
        assert fresh.execute("SELECT COUNT(*) FROM memories").fetchone()[0] == 1


def test_concurrent_writers_all_persist_under_contention(tmp_path) -> None:
    database_path = tmp_path / "dma.db"
    SQLiteMemoryRepository(database_path).initialize()
    repository = SQLiteMemoryRepository(database_path)

    def write(index: int) -> None:
        repository.create_or_get(_record(index), f"idempotency-concurrency-{index:04d}")

    threads = [threading.Thread(target=write, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

    assert count == 8


def _legacy_database(path) -> None:
    """Create a pre-agent-scope database: idempotency rows lack agent_id."""
    from datetime import UTC, datetime

    now = datetime(2026, 8, 27, tzinfo=UTC).isoformat()
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                content TEXT NOT NULL,
                content_normalized TEXT,
                type TEXT NOT NULL CHECK(type IN ('episodic', 'semantic', 'procedural')),
                version INTEGER NOT NULL CHECK(version >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT,
                metadata_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE memory_search USING fts5(
                content,
                memory_id UNINDEXED,
                tenant_id UNINDEXED,
                agent_id UNINDEXED,
                type UNINDEXED,
                tokenize = 'unicode61'
            );
            CREATE TABLE idempotency_keys (
                tenant_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                memory_id TEXT NOT NULL REFERENCES memories(id),
                created_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, operation, idempotency_key)
            );
            """
        )
        connection.execute(
            "INSERT INTO memories (id, tenant_id, agent_id, content, content_normalized,"
            " type, version, created_at, updated_at, expires_at, metadata_json)"
            " VALUES ('mem_legacy00000000000001', 'tenant-a', 'coding-agent',"
            " 'Legacy pytest preference.', 'legacy pytest preference.', 'episodic', 1, ?, ?, NULL, '{}')",
            (now, now),
        )
        connection.execute(
            "INSERT INTO memory_search (content, memory_id, tenant_id, agent_id, type)"
            " VALUES ('Legacy pytest preference.', 'mem_legacy00000000000001', 'tenant-a', 'coding-agent', 'episodic')"
        )
        connection.execute(
            "INSERT INTO idempotency_keys (tenant_id, operation, idempotency_key, memory_id, created_at)"
            " VALUES ('tenant-a', 'remember', 'legacy-shared-key-01', 'mem_legacy00000000000001', ?)",
            (now,),
        )


def test_initialize_scopes_legacy_idempotency_keys_to_the_agent(tmp_path) -> None:
    database_path = tmp_path / "dma.db"
    _legacy_database(database_path)
    repository = SQLiteMemoryRepository(database_path)
    repository.initialize()

    with sqlite3.connect(database_path) as connection:
        key_columns = {row[1] for row in connection.execute("PRAGMA table_info(idempotency_keys)").fetchall() if row[5] > 0}
        owner = connection.execute(
            "SELECT agent_id FROM idempotency_keys WHERE idempotency_key = 'legacy-shared-key-01'"
        ).fetchone()[0]

    assert {"tenant_id", "agent_id", "operation", "idempotency_key"} <= key_columns
    assert owner == "coding-agent"

    from datetime import UTC, datetime

    now = datetime(2026, 8, 28, tzinfo=UTC)
    replay = MemoryRecord(
        id="mem_replay00000000000001",
        tenant_id="tenant-a",
        agent_id="coding-agent",
        content="Unrelated replay content.",
        type=MemoryType.EPISODIC,
        version=1,
        created_at=now,
        updated_at=now,
        expires_at=None,
        metadata={},
    )
    other_agent = MemoryRecord(
        id="mem_other000000000000001",
        tenant_id="tenant-a",
        agent_id="research-agent",
        content="Research agent note.",
        type=MemoryType.EPISODIC,
        version=1,
        created_at=now,
        updated_at=now,
        expires_at=None,
        metadata={},
    )
    stored_replay, created_replay = repository.create_or_get(replay, "legacy-shared-key-01")
    stored_other, created_other = repository.create_or_get(other_agent, "legacy-shared-key-01")

    assert created_replay is False
    assert stored_replay.id == "mem_legacy00000000000001"
    assert created_other is True
    assert stored_other.id == "mem_other000000000000001"
