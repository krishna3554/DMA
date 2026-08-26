from __future__ import annotations

from fastapi.testclient import TestClient

from dma_api.config import Settings
from dma_api.main import create_app


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "Idempotency-Key": "remember-request-0001",
    }


def test_remember_persists_a_typed_memory(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        response = client.post(
            "/v1/memories",
            headers=_headers(),
            json={
                "agent_id": "coding-agent",
                "content": "User prefers Java Spring Boot.",
                "type": "semantic",
                "metadata": {"source": "chat"},
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["id"].startswith("mem_")
    assert body["type"] == "semantic"
    assert body["version"] == 1
    assert body["metadata"] == {"source": "chat"}


def test_remember_replays_an_idempotency_key(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    payload = {"agent_id": "coding-agent", "content": "Use pytest.", "type": "procedural"}
    with TestClient(app) as client:
        first = client.post("/v1/memories", headers=_headers(), json=payload)
        second = client.post("/v1/memories", headers=_headers(), json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]


def test_remember_versions_duplicate_semantic_memory(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    payload = {"agent_id": "coding-agent", "content": "User prefers Java Spring Boot.", "type": "semantic"}
    with TestClient(app) as client:
        first = client.post("/v1/memories", headers={**_headers(), "Idempotency-Key": "semantic-first-0001"}, json=payload)
        second = client.post("/v1/memories", headers={**_headers(), "Idempotency-Key": "semantic-second-001"}, json={**payload, "content": "  user prefers java spring boot. "})

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["version"] == 2


def test_remember_requires_valid_authentication(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key"))
    with TestClient(app) as client:
        response = client.post(
            "/v1/memories",
            headers={"Idempotency-Key": "remember-request-0001"},
            json={"agent_id": "coding-agent", "content": "A fact", "type": "semantic"},
        )

    assert response.status_code == 401


def test_remember_rejects_a_wrong_api_key(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key"))
    with TestClient(app) as client:
        response = client.post(
            "/v1/memories",
            headers={"Authorization": "Bearer wrong-key", "Idempotency-Key": "remember-request-0001"},
            json={"agent_id": "coding-agent", "content": "A fact", "type": "semantic"},
        )

    assert response.status_code == 401
