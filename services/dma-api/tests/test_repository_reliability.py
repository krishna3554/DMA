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
