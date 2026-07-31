from __future__ import annotations

from fastapi.testclient import TestClient

from dma_api.config import Settings
from dma_api.main import create_app


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": "Bearer test-key", "Idempotency-Key": key}


def _remember(client: TestClient, content: str, key: str) -> str:
    response = client.post(
        "/v1/memories",
        headers=_headers(key),
        json={"agent_id": "coding-agent", "content": content, "type": "semantic"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_list_uses_a_stable_cursor(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        _remember(client, "First Java preference.", "list-key-00000001")
        _remember(client, "Second Java preference.", "list-key-00000002")
        _remember(client, "Third Java preference.", "list-key-00000003")
        first_page = client.get(
            "/v1/memories?agent_id=coding-agent&limit=2", headers={"Authorization": "Bearer test-key"}
        )
        cursor = first_page.json()["next_cursor"]
        second_page = client.get(
            f"/v1/memories?agent_id=coding-agent&limit=2&cursor={cursor}",
            headers={"Authorization": "Bearer test-key"},
        )

    assert first_page.status_code == 200
    assert len(first_page.json()["items"]) == 2
    assert cursor is not None
    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1
    first_ids = {item["id"] for item in first_page.json()["items"]}
    second_ids = {item["id"] for item in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_explain_and_forget_are_scoped_to_the_agent(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db", api_key="test-key", tenant_id="tenant-a"))
    with TestClient(app) as client:
        memory_id = _remember(client, "User prefers Java for backend development.", "admin-key-0000001")
        explanation = client.get(
            f"/v1/memories/{memory_id}/explanation?agent_id=coding-agent&query=Java+backend",
            headers={"Authorization": "Bearer test-key"},
        )
        deletion = client.delete(
            f"/v1/memories/{memory_id}?agent_id=coding-agent",
            headers={"Authorization": "Bearer test-key"},
        )
        after_deletion = client.get(
            f"/v1/memories/{memory_id}/explanation?agent_id=coding-agent",
            headers={"Authorization": "Bearer test-key"},
        )

    assert explanation.status_code == 200
    assert explanation.json()["retrieval"] == {
        "strategy": "lexical_fts5_bm25",
        "matched_terms": ["Java", "backend"],
        "filters_applied": ["tenant_id", "agent_id", "expires_at"],
    }
    assert deletion.status_code == 204
    assert after_deletion.status_code == 404
