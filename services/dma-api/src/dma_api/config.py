"""Service configuration with safe local-development defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings passed explicitly to the application factory."""

    database_path: Path = Path("./dma.db")
    api_key: str = "dma-local-development-key"
    tenant_id: str = "local"
