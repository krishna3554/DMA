from __future__ import annotations

import json

import httpx
import pytest

from dma import AuthenticationError, DMAApiError, DMAClient, MemoryType, ValidationError


def _memory_payload() -> dict[str, object]:
    return {
        "id": "mem_abc123",
        "agent_id": "coding-agent",
        "content": "User prefers Java Spring Boot.",
        "type": "semantic",
        "version": 1,
        "status": "active",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "expires_at": None,
        "metadata": {"source": "chat"},
    }


def _client(handler) -> DMAClient:
    return DMAClient(
        api_key="test-key",
        agent_id="coding-agent",
        base_url="https://dma.test",
        transport=httpx.MockTransport(handler),
    )


def test_remember_sends_agent_scope_and_idempotency_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/memories"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert len(request.headers["Idempotency-Key"]) >= 16
        assert json.loads(request.content) == {
            "agent_id": "coding-agent",
            "content": "User prefers Java Spring Boot.",
            "type": "semantic",
            "metadata": {"source": "chat"},
        }
        return httpx.Response(201, json=_memory_payload())

    client = _client(handler)
    memory = client.remember(
        content="User prefers Java Spring Boot.", type=MemoryType.SEMANTIC, metadata={"source": "chat"}
    )
    assert memory.id == "mem_abc123"
    assert memory.type is MemoryType.SEMANTIC


def test_recall_and_explain_return_typed_models() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/recall"):
            result = _memory_payload() | {"score": 0.75}
            return httpx.Response(200, json={"results": [result]})
        return httpx.Response(
            200,
            json={
                "memory_id": "mem_abc123",
                "type": "semantic",
                "version": 1,
                "status": "active",
                "retrieval": {
                    "strategy": "lexical_fts5_bm25",
                    "matched_terms": ["Java"],
                    "filters_applied": ["tenant_id", "agent_id", "expires_at"],
                },
            },
        )

    client = _client(handler)
    results = client.recall(query="Which Java backend?")
    explanation = client.explain("mem_abc123", query="Java")
    assert results[0].score == 0.75
    assert explanation.retrieval.matched_terms == ["Java"]


def test_client_surfaces_auth_and_api_errors() -> None:
    auth_client = _client(lambda _: httpx.Response(401, json={"detail": "invalid API key"}))
    with pytest.raises(AuthenticationError):
        auth_client.recall(query="Java")

    api_client = _client(lambda _: httpx.Response(404, json={"detail": "memory not found"}))
    with pytest.raises(DMAApiError, match="memory not found"):
        api_client.forget("mem_missing")


def test_client_validates_inputs_before_requests() -> None:
    with pytest.raises(ValidationError, match="api_key"):
        DMAClient(api_key=" ", agent_id="coding-agent")
    client = _client(lambda _: pytest.fail("should not issue a request"))
    with pytest.raises(ValidationError, match="content"):
        client.remember(content=" ", type="semantic")
    with pytest.raises(ValidationError, match="type must"):
        client.remember(content="fact", type="invalid")
