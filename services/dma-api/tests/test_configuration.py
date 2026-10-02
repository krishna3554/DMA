from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from dma_api.config import Settings
from dma_api.main import create_app


def test_production_rejects_default_local_key(monkeypatch) -> None:
    monkeypatch.setenv("DMA_ENVIRONMENT", "production")
    monkeypatch.delenv("DMA_API_KEY", raising=False)

    with pytest.raises(ValueError, match="DMA_API_KEY"):
        Settings.from_env()


def test_health_endpoint_is_unauthenticated(tmp_path) -> None:
    app = create_app(Settings(database_path=tmp_path / "dma.db"))
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_invalid_auth_limit_env_values_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DMA_AUTH_LOCKOUT_SECONDS", "0")

    with pytest.raises(ValueError, match="DMA_AUTH_LOCKOUT_SECONDS"):
        Settings.from_env()


def test_non_numeric_auth_limit_env_values_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("DMA_AUTH_MAX_ATTEMPTS", "many")

    with pytest.raises(ValueError, match="DMA_AUTH_MAX_ATTEMPTS"):
        Settings.from_env()


def test_forwarded_for_is_untrusted_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DMA_TRUST_FORWARDED_FOR", raising=False)

    assert Settings.from_env().trust_forwarded_for is False


def _small_settings(tmp_path, **overrides):
    return Settings(database_path=tmp_path / "dma.db", api_key="test-key", max_request_bytes=1024, **overrides)


def _remember_payload(content: str) -> bytes:
    return json.dumps({"agent_id": "coding-agent", "content": content, "type": "semantic"}).encode()


def _auth_headers(key: str) -> dict[str, str]:
    return {"Authorization": "Bearer test-key", "Idempotency-Key": key, "Content-Type": "application/json"}


def test_declared_content_length_over_limit_is_rejected(tmp_path) -> None:
    app = create_app(_small_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/v1/memories", headers=_auth_headers("length-key-00000001"), content=_remember_payload("x" * 2048)
        )

    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_chunked_body_over_limit_is_rejected(tmp_path) -> None:
    """A body without Content-Length (chunked) must be measured, not trusted."""
    app = create_app(_small_settings(tmp_path))
    payload = _remember_payload("y" * 2048)

    def chunks():
        yield payload[:512]
        yield payload[512:1024]
        yield payload[1024:]

    with TestClient(app) as client:
        response = client.post("/v1/memories", headers=_auth_headers("chunked-key-000001"), content=chunks())

    assert "content-length" not in {key.lower() for key in response.request.headers}
    assert response.status_code == 413
    assert response.headers["content-type"] == "application/problem+json"


def test_chunked_body_under_limit_is_replayed_intact(tmp_path) -> None:
    app = create_app(_small_settings(tmp_path))
    payload = _remember_payload("A small under-limit preference.")

    def chunks():
        yield payload[:10]
        yield payload[10:]

    with TestClient(app) as client:
        response = client.post("/v1/memories", headers=_auth_headers("chunked-key-000002"), content=chunks())

    assert response.status_code == 201
    assert response.json()["content"] == "A small under-limit preference."


def test_chunked_body_is_counted_across_messages(tmp_path) -> None:
    """Drive the ASGI app directly with several more_body messages over the limit."""
    database_path = tmp_path / "dma.db"
    app = create_app(_small_settings(tmp_path))
    from dma_api.repository import SQLiteMemoryRepository

    SQLiteMemoryRepository(database_path).initialize()
    payload = _remember_payload("z" * 2048)
    first, second, third = payload[:400], payload[400:800], payload[800:]
    messages = [
        {"type": "http.request", "body": first, "more_body": True},
        {"type": "http.request", "body": second, "more_body": True},
        {"type": "http.request", "body": third, "more_body": False},
    ]
    sent: list[dict] = []

    async def receive():
        if messages:
            return messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/memories",
        "raw_path": b"/v1/memories",
        "query_string": b"",
        "headers": [
            (b"authorization", b"Bearer test-key"),
            (b"idempotency-key", b"asgi-chunked-key-01"),
            (b"content-type", b"application/json"),
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "extensions": {},
    }
    asyncio.run(app(scope, receive, send))

    statuses = [message["status"] for message in sent if message["type"] == "http.response.start"]
    assert statuses == [413]
