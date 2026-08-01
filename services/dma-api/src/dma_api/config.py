"""Service configuration with safe local-development defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings passed explicitly to the application factory."""

    database_path: Path = Path("./dma.db")
    api_key: str = "dma-local-development-key"
    tenant_id: str = "local"

    @classmethod
    def from_env(cls) -> Settings:
        """Load runtime configuration without ever logging secret values."""
        return cls(
            database_path=Path(os.getenv("DMA_DATABASE_PATH", "./dma.db")),
            api_key=os.getenv("DMA_API_KEY", "dma-local-development-key"),
            tenant_id=os.getenv("DMA_TENANT_ID", "local"),
        )
