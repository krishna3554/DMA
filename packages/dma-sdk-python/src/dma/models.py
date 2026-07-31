"""Public result models returned by the DMA SDK."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass(frozen=True, slots=True)
class Memory:
    id: str
    agent_id: str
    content: str
    type: MemoryType
    version: int
    status: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RecallResult(Memory):
    score: float


@dataclass(frozen=True, slots=True)
class MemoryPage:
    items: list[Memory]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RetrievalExplanation:
    strategy: str
    matched_terms: list[str]
    filters_applied: list[str]


@dataclass(frozen=True, slots=True)
class MemoryExplanation:
    memory_id: str
    type: MemoryType
    version: int
    status: str
    retrieval: RetrievalExplanation
