"""Domain and transport models for the DMA API."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

# Hard ceilings enforced at the model layer for every caller. The operational
# limit defaults to 16 KiB via Settings (DMA_MAX_METADATA_BYTES) and is checked
# in the endpoint so operators can tighten it; the model keeps a higher hard
# ceiling so a misconfigured large Settings value cannot allow unbounded
# multi-MB allocations through the API.
MAX_METADATA_HARD_BYTES = 64 * 1024
MAX_METADATA_DEPTH = 10


def metadata_depth(value: Any, _level: int = 1) -> int:
    """Return the nesting depth of a JSON-like value (scalars count as 1)."""
    if isinstance(value, dict):
        if not value:
            return _level
        return max(metadata_depth(item, _level + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return _level
        return max(metadata_depth(item, _level + 1) for item in value)
    return _level


def metadata_serialized_size(metadata: dict[str, Any]) -> int:
    return len(json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode("utf-8"))


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class RememberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=20_000)
    type: MemoryType
    expires_at: AwareDatetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id", "content")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_future(cls, value: datetime | None) -> datetime | None:
        if value is not None and value <= datetime.now(UTC):
            raise ValueError("must be in the future")
        return value

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        if metadata_depth(value) > MAX_METADATA_DEPTH:
            raise ValueError(f"metadata nesting must not exceed {MAX_METADATA_DEPTH} levels")
        if metadata_serialized_size(value) > MAX_METADATA_HARD_BYTES:
            raise ValueError(
                f"metadata must not exceed {MAX_METADATA_HARD_BYTES} bytes when serialized"
            )
        return value


class MemoryResponse(BaseModel):
    id: str
    agent_id: str
    content: str
    type: MemoryType
    version: int
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    metadata: dict[str, Any]


class RecallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=20_000)
    types: list[MemoryType] | None = Field(
        default=None,
        description="Filter by memory types. Omitted or an empty list means all types.",
    )
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator("agent_id", "query")
    @classmethod
    def recall_fields_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class RecallResult(MemoryResponse):
    score: float = Field(
        ge=0,
        le=1,
        description=(
            "Relative relevance within this single response only: scores are "
            "normalized by the top hit, so the best match is always 1.0. "
            "Do not compare across queries or treat as calibrated confidence."
        ),
    )


class RecallResponse(BaseModel):
    results: list[RecallResult]


class MemoryPage(BaseModel):
    items: list[MemoryResponse]
    next_cursor: str | None = None


class RetrievalExplanation(BaseModel):
    strategy: str
    matched_terms: list[str] = Field(default_factory=list)
    filters_applied: list[str]


class MemoryExplanation(BaseModel):
    memory_id: str
    type: MemoryType
    version: int
    status: str
    retrieval: RetrievalExplanation
