"""Service configuration with safe local-development defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dma_api.repository import AnalyzerKind


@dataclass(frozen=True, slots=True)
class AuthLimits:
    """Rate-limiting bounds for bearer-auth attempts per source (IP)."""

    max_attempts: int = 5
    window_seconds: int = 60
    lockout_seconds: int = 300
    max_tracked_sources: int = 10_000

    def __post_init__(self) -> None:
        for name in ("max_attempts", "window_seconds", "lockout_seconds", "max_tracked_sources"):
            value = getattr(self, name)
            if value < 1:
                raise ValueError(f"{name} must be a positive integer, got {value}")


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer, got {value}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings passed explicitly to the application factory."""

    database_path: Path = Path("./dma.db")
    api_key: str = "dma-local-development-key"
    tenant_id: str = "local"
    environment: str = "development"
    analyzer_kind: AnalyzerKind = AnalyzerKind.PLAIN
    auth_limits: AuthLimits = field(default_factory=AuthLimits)
    trust_forwarded_for: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        """Load runtime configuration without ever logging secret values."""
        limits = AuthLimits(
            max_attempts=_positive_int_env("DMA_AUTH_MAX_ATTEMPTS", 5),
            window_seconds=_positive_int_env("DMA_AUTH_WINDOW_SECONDS", 60),
            lockout_seconds=_positive_int_env("DMA_AUTH_LOCKOUT_SECONDS", 300),
            max_tracked_sources=_positive_int_env("DMA_AUTH_MAX_TRACKED_SOURCES", 10_000),
        )
        analyzer_kind_str = os.getenv("DMA_ANALYZER_KIND", "plain").lower()
        try:
            analyzer_kind = AnalyzerKind(analyzer_kind_str)
        except ValueError:
            analyzer_kind = AnalyzerKind.PLAIN
        settings = cls(
            database_path=Path(os.getenv("DMA_DATABASE_PATH", "./dma.db")),
            api_key=os.getenv("DMA_API_KEY", "dma-local-development-key"),
            tenant_id=os.getenv("DMA_TENANT_ID", "local"),
            environment=os.getenv("DMA_ENVIRONMENT", "development"),
            analyzer_kind=analyzer_kind,
            auth_limits=limits,
            trust_forwarded_for=os.getenv("DMA_TRUST_FORWARDED_FOR", "false").lower()
            in {"1", "true", "yes"},
        )
        if settings.environment == "production" and settings.api_key == "dma-local-development-key":
            raise ValueError("DMA_API_KEY must be explicitly configured in production")
        return settings
