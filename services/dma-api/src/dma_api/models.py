"""Domain and transport models for the DMA API."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(StrEnum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class RememberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=20_000)
    type: MemoryType
    expires_at: datetime | None = None
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
