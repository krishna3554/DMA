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

    assert response.status_code == 200
    contents = [item["content"] for item in response.json()["results"]]
    assert contents == ["User now prefers Java Spring Boot for backend APIs."]


def test_recall_prefix_only_matching_no_false_positives(tmp_path) -> None:
    """Adversarial tests for prefix-only token matching.

    The old bidirectional substring matching caused false positives:
    - 'api' matched 'rapid' (substring but not prefix)
    - 'art' matched 'particle' (substring but not prefix)

    Prefix-only matching ensures:
    - 'api' matches 'api' (exact) and 'apikey' (prefix), but NOT 'rapid'
    - 'art' matches 'art' (exact) and 'artist' (prefix), but NOT 'particle'
    - 'cat' matches 'cat', 'cater', 'category' (all valid prefixes)
    """
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        # Store memories with words that could cause false positives with substring matching
        _remember(client, "Rapid deployment is our goal.", "semantic", "key-cat-0000000002")
        _remember(client, "Particle physics is complex.", "semantic", "key-cat-0000000003")
        # Also store exact/prefix matches that SHOULD be found
        _remember(client, "API key configuration done.", "semantic", "key-cat-0000000005")
        _remember(client, "Artist portfolio updated.", "semantic", "key-cat-0000000006")
        # 'cat' prefix matches are legitimate - store some
        _remember(client, "The cat sits on the mat.", "semantic", "key-cat-0000000004")
        _remember(client, "The category system organizes items.", "semantic", "key-cat-0000000001")

        # Query 'api' should NOT match 'rapid' (substring), but SHOULD match 'api' and 'apikey'
        response = client.post(
            "/v1/memories/recall",
            headers={"Authorization": "Bearer test-key"},
            json={"agent_id": "coding-agent", "query": "api", "limit": 10},
        )
    assert response.status_code == 200
    results = response.json()["results"]
    contents = [item["content"] for item in results]
    assert "API key configuration done." in contents
    assert "Rapid deployment is our goal." not in contents

    # Query 'art' should NOT match 'particle' (substring), but SHOULD match 'art' and 'artist'
    response = client.post(
        "/v1/memories/recall",
        headers={"Authorization": "Bearer test-key"},
        json={"agent_id": "coding-agent", "query": "art", "limit": 10},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    contents = [item["content"] for item in results]
    assert "Artist portfolio updated." in contents
    assert "Particle physics is complex." not in contents

    # Query 'cat' matches 'cat', 'cater', 'category' (all valid prefixes)
    response = client.post(
        "/v1/memories/recall",
        headers={"Authorization": "Bearer test-key"},
        json={"agent_id": "coding-agent", "query": "cat", "limit": 10},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    contents = [item["content"] for item in results]
    # Both should match since 'cat' is a prefix of 'category'
    assert "The cat sits on the mat." in contents
    assert "The category system organizes items." in contents
