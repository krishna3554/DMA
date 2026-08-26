from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from dma_api.config import Settings
from dma_api.main import create_app


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


def test_recall_falls_back_when_current_marker_filter_empties_results(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        _remember(client, "The database password is hunter2.", "semantic", "key-000000000005")
        response = client.post(
            "/v1/memories/recall",
            headers={"Authorization": "Bearer test-key"},
            json={"agent_id": "coding-agent", "query": "What is the latest database password?", "limit": 5},
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["content"] == "The database password is hunter2."


def test_recall_prefers_current_state_memories_for_now_queries(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        _remember(client, "User preferred Django for backend APIs.", "semantic", "key-000000000006")
        _remember(client, "User now prefers Java Spring Boot for backend APIs.", "semantic", "key-000000000007")
        response = client.post(
            "/v1/memories/recall",
            headers={"Authorization": "Bearer test-key"},
            json={"agent_id": "coding-agent", "query": "What backend framework does the user prefer now?", "limit": 5},
        )

    assert response.status_code == 200
    contents = [item["content"] for item in response.json()["results"]]
    assert contents == ["User now prefers Java Spring Boot for backend APIs."]
