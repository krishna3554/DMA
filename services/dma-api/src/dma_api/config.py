"""Service configuration with safe local-development defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dma_api.repository import AnalyzerKind


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings passed explicitly to the application factory."""

    database_path: Path = Path("./dma.db")
    api_key: str = "dma-local-development-key"
    tenant_id: str = "local"
    environment: str = "development"
    analyzer_kind: AnalyzerKind = AnalyzerKind.PLAIN

    @classmethod
    def from_env(cls) -> Settings:
        """Load runtime configuration without ever logging secret values."""
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
        )
        if settings.environment == "production" and settings.api_key == "dma-local-development-key":
            raise ValueError("DMA_API_KEY must be explicitly configured in production")
        return settings
