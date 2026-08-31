from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dma_api.config import AuthLimits, Settings
from dma_api.main import InMemoryRateLimiter, create_app


def _settings(tmp_path, limits: AuthLimits, *, trust_forwarded_for: bool = True) -> Settings:
    return Settings(
        database_path=tmp_path / "dma.db",
        api_key="test-key",
        auth_limits=limits,
        trust_forwarded_for=trust_forwarded_for,
    )


def _bad_auth_headers(source: str = "10.0.0.1") -> dict[str, str]:
    return {
        "Authorization": "Bearer wrong-key",
        "Idempotency-Key": "rate-limit-test-00001",
        "X-Forwarded-For": source,
    }


def _good_auth_headers(source: str = "10.0.0.1") -> dict[str, str]:
    return {
        "Authorization": "Bearer test-key",
        "Idempotency-Key": "rate-limit-test-00001",
        "X-Forwarded-For": source,
    }


def _json() -> dict[str, str]:
    return {"agent_id": "coding-agent", "content": "A fact.", "type": "semantic"}


def test_lockout_after_max_failed_attempts(tmp_path) -> None:
    limits = AuthLimits(max_attempts=3, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    with TestClient(app) as client:
        for _ in range(3):
            resp = client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())
            assert resp.status_code == 401

        resp = client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())
        assert resp.status_code == 429
        assert "too many" in resp.json()["detail"]


def test_lockout_blocks_valid_key_from_same_source(tmp_path) -> None:
    limits = AuthLimits(max_attempts=2, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    with TestClient(app) as client:
        for _ in range(2):
            client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())

        resp = client.post("/v1/memories", headers=_good_auth_headers(), json=_json())
        assert resp.status_code == 429


def test_lockout_does_not_affect_other_sources(tmp_path) -> None:
    limits = AuthLimits(max_attempts=2, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    with TestClient(app) as client:
        for _ in range(2):
            client.post("/v1/memories", headers=_bad_auth_headers("10.0.0.1"), json=_json())

        resp = client.post("/v1/memories", headers=_good_auth_headers("10.0.0.2"), json=_json())
        assert resp.status_code == 201


def test_successful_auth_resets_failure_count(tmp_path) -> None:
    limits = AuthLimits(max_attempts=3, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    with TestClient(app) as client:
        for _ in range(2):
            client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())

        resp = client.post("/v1/memories", headers=_good_auth_headers(), json=_json())
        assert resp.status_code == 201

        for _ in range(2):
            client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())

        resp = client.post(
            "/v1/memories",
            headers={**_good_auth_headers(), "Idempotency-Key": "rate-limit-test-00002"},
            json=_json(),
        )
        assert resp.status_code in (200, 201)


def test_lockout_expires_after_lockout_seconds() -> None:
    limits = AuthLimits(max_attempts=2, window_seconds=60, lockout_seconds=10)
    limiter = InMemoryRateLimiter(limits)

    limiter.record_failure("src")
    limiter.record_failure("src")
    assert limiter.is_locked_out("src")

    with patch("dma_api.main.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 11
        assert not limiter.is_locked_out("src")


def test_failures_outside_window_do_not_count() -> None:
    limits = AuthLimits(max_attempts=3, window_seconds=5, lockout_seconds=300)
    limiter = InMemoryRateLimiter(limits)

    limiter.record_failure("src")
    limiter.record_failure("src")
    assert not limiter.is_locked_out("src")

    original_monotonic = time.monotonic

    def shifted_time():
        return original_monotonic() + 6

    with patch("dma_api.main.time") as mock_time:
        mock_time.monotonic = shifted_time
        limiter.record_failure("src")
        assert not limiter.is_locked_out("src")


def test_healthz_not_rate_limited(tmp_path) -> None:
    limits = AuthLimits(max_attempts=1, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    with TestClient(app) as client:
        client.post("/v1/memories", headers=_bad_auth_headers(), json=_json())

        resp = client.get("/healthz")
        assert resp.status_code == 200


def test_auth_failure_logged(tmp_path, caplog) -> None:
    limits = AuthLimits(max_attempts=5, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits))
    import logging
    with caplog.at_level(logging.WARNING, logger="dma_api.auth"), TestClient(app) as client:
        client.post("/v1/memories", headers=_bad_auth_headers("192.168.1.1"), json=_json())

    assert any("auth_failure" in record.message and "192.168.1.1" in record.message for record in caplog.records)


def test_forwarded_for_is_ignored_when_proxy_is_untrusted(tmp_path) -> None:
    limits = AuthLimits(max_attempts=2, window_seconds=60, lockout_seconds=300)
    app = create_app(_settings(tmp_path, limits, trust_forwarded_for=False))
    with TestClient(app) as client:
        for index in range(2):
            client.post("/v1/memories", headers=_bad_auth_headers(f"10.0.0.{index}"), json=_json())

        resp = client.post("/v1/memories", headers=_good_auth_headers("10.0.0.9"), json=_json())
        assert resp.status_code == 429


def test_stale_sources_are_evicted() -> None:
    limits = AuthLimits(max_attempts=5, window_seconds=5, lockout_seconds=10)
    limiter = InMemoryRateLimiter(limits)

    for index in range(50):
        limiter.record_failure(f"10.0.0.{index}")
    assert limiter.tracked_sources() == 50

    original_monotonic = time.monotonic
    with patch("dma_api.main.time") as mock_time:
        mock_time.monotonic = lambda: original_monotonic() + 60
        limiter.record_failure("10.1.0.1")

    assert limiter.tracked_sources() == 1


def test_locked_out_sources_survive_eviction() -> None:
    limits = AuthLimits(max_attempts=2, window_seconds=5, lockout_seconds=300)
    limiter = InMemoryRateLimiter(limits)

    limiter.record_failure("attacker")
    limiter.record_failure("attacker")
    assert limiter.is_locked_out("attacker")

    original_monotonic = time.monotonic
    with patch("dma_api.main.time") as mock_time:
        mock_time.monotonic = lambda: original_monotonic() + 60
        limiter.record_failure("someone-else")
        assert limiter.is_locked_out("attacker")


def test_tracked_sources_stay_within_configured_maximum() -> None:
    limits = AuthLimits(
        max_attempts=5, window_seconds=600, lockout_seconds=300, max_tracked_sources=10
    )
    limiter = InMemoryRateLimiter(limits)

    for index in range(100):
        limiter.record_failure(f"10.0.0.{index}")

    assert limiter.tracked_sources() <= 10


def test_non_positive_auth_limits_are_rejected() -> None:
    with pytest.raises(ValueError, match="lockout_seconds"):
        AuthLimits(max_attempts=5, window_seconds=60, lockout_seconds=0)
    with pytest.raises(ValueError, match="max_attempts"):
        AuthLimits(max_attempts=0, window_seconds=60, lockout_seconds=300)
