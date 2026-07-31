"""FastAPI application for DMA."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status

from dma_api.config import Settings
from dma_api.models import (
    MemoryResponse,
    RecallRequest,
    RecallResponse,
    RecallResult,
    RememberRequest,
)
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable API application."""
    runtime_settings = settings or Settings()
    repository = SQLiteMemoryRepository(runtime_settings.database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(title="DMA API", version="0.1.0", lifespan=lifespan)

    def authenticate(authorization: str | None = Header(default=None)) -> str:
        expected = f"Bearer {runtime_settings.api_key}"
        if authorization != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
        return runtime_settings.tenant_id

    @app.post("/v1/memories", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
    def remember(
        payload: RememberRequest,
        response: Response,
        idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=16, max_length=255),
        tenant_id: str = Depends(authenticate),
    ) -> MemoryResponse:
        now = datetime.now(UTC)
        record = MemoryRecord(
            id=f"mem_{uuid4().hex}",
            tenant_id=tenant_id,
            agent_id=payload.agent_id,
            content=payload.content,
            type=payload.type,
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=payload.expires_at,
            metadata=payload.metadata,
        )
        stored, created = repository.create_or_get(record, idempotency_key)
        if not created:
            response.status_code = status.HTTP_200_OK
        return MemoryResponse(
            id=stored.id,
            agent_id=stored.agent_id,
            content=stored.content,
            type=stored.type,
            version=stored.version,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
            expires_at=stored.expires_at,
            metadata=stored.metadata,
        )

    @app.post("/v1/memories/recall", response_model=RecallResponse)
    def recall(payload: RecallRequest, tenant_id: str = Depends(authenticate)) -> RecallResponse:
        matches = repository.recall(
            tenant_id=tenant_id,
            agent_id=payload.agent_id,
            query=payload.query,
            types=payload.types,
            limit=payload.limit,
            now=datetime.now(UTC),
        )
        return RecallResponse(
            results=[
                RecallResult(
                    id=memory.id,
                    agent_id=memory.agent_id,
                    content=memory.content,
                    type=memory.type,
                    version=memory.version,
                    created_at=memory.created_at,
                    updated_at=memory.updated_at,
                    expires_at=memory.expires_at,
                    metadata=memory.metadata,
                    score=score,
                )
                for memory, score in matches
            ]
        )

    return app


app = create_app()
