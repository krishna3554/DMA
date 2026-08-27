from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from dma_api.config import Settings
from dma_api.main import create_app
from dma_api.models import MemoryType
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": "Bearer test-key", "Idempotency-Key": key}


def _remember(client: TestClient, content: str, memory_type: str, key: str, **extra: object) -> None:
    response = client.post(
        "/v1/memories",
        headers=_headers(key),
        json={"agent_id": "coding-agent", "content": content, "type": memory_type, **extra},
    )
    assert response.status_code == 201


def test_recall_returns_ranked_scoped_results(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        _remember(client, "User prefers Java Spring Boot for backend work.", "semantic", "key-000000000001")
        _remember(client, "User likes hiking on weekends.", "semantic", "key-000000000002")
        response = client.post(
            "/v1/memories/recall",
            headers={"Authorization": "Bearer test-key"},
            json={"agent_id": "coding-agent", "query": "preferred Java backend", "limit": 3},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["content"] == "User prefers Java Spring Boot for backend work."
    assert 0 <= results[0]["score"] <= 1


def test_recall_excludes_expired_and_non_matching_types(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    expired = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    with TestClient(app) as client:
        _remember(client, "Deploy using the Java release workflow.", "procedural", "key-000000000003")
        _remember(
            client,
            "Java incident from last week.",
            "episodic",
            "key-000000000004",
            expires_at=expired,
        )
        response = client.post(
            "/v1/memories/recall",
            headers={"Authorization": "Bearer test-key"},
            json={"agent_id": "coding-agent", "query": "Java", "types": ["procedural"]},
        )

    assert response.status_code == 200
    assert [item["type"] for item in response.json()["results"]] == ["procedural"]


def test_recall_includes_memories_expiring_after_now_regardless_of_offset(tmp_path) -> None:
    """A non-UTC expiry must not be treated as expired by lexical comparison."""
    repository = SQLiteMemoryRepository(tmp_path / "dma.db")
    repository.initialize()
    now = datetime(2026, 8, 27, 20, 0, 0, tzinfo=UTC)
    expires_soon = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone(timedelta(hours=-11)))
    assert expires_soon.astimezone(UTC) > now
    repository.create_or_get(
        MemoryRecord(
            id="mem_offsetexpiry00000000000001",
            tenant_id="tenant-a",
            agent_id="coding-agent",
            content="Staging cluster deployment notes.",
            type=MemoryType.EPISODIC,
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=expires_soon,
            metadata={},
        ),
        "idempotency-offset-expiry-0001",
    )

    matches = repository.recall(
        tenant_id="tenant-a",
        agent_id="coding-agent",
        query="staging cluster deployment",
        types=None,
        limit=5,
        now=now,
    )

    assert [record.id for record, _ in matches] == ["mem_offsetexpiry00000000000001"]
