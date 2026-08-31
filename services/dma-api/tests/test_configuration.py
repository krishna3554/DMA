from __future__ import annotations

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
