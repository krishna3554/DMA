"""FastAPI application for DMA."""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status

from dma_api.config import Settings
from dma_api.models import (
    MemoryExplanation,
    MemoryPage,
    MemoryResponse,
    MemoryType,
    RecallRequest,
    RecallResponse,
    RecallResult,
    RememberRequest,
    RetrievalExplanation,
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
        return _to_memory_response(stored, now)

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
                RecallResult(**_to_memory_response(memory, datetime.now(UTC)).model_dump(), score=score)
                for memory, score in matches
            ]
        )

    @app.get("/v1/memories", response_model=MemoryPage)
    def list_memories(
        agent_id: str = Query(min_length=1, max_length=128),
        type: MemoryType | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        cursor: str | None = None,
        tenant_id: str = Depends(authenticate),
    ) -> MemoryPage:
        try:
            memories, next_cursor = repository.list_memories(
                tenant_id=tenant_id,
                agent_id=agent_id,
                memory_type=type,
                limit=limit,
                cursor=cursor,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        now = datetime.now(UTC)
        return MemoryPage(
            items=[_to_memory_response(memory, now) for memory in memories], next_cursor=next_cursor
        )

    @app.delete("/v1/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
    def forget(memory_id: str, agent_id: str, tenant_id: str = Depends(authenticate)) -> Response:
        if not repository.delete(tenant_id=tenant_id, agent_id=agent_id, memory_id=memory_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/v1/memories/{memory_id}/explanation", response_model=MemoryExplanation)
    def explain(
        memory_id: str,
        agent_id: str,
        query: str | None = Query(default=None, max_length=20_000),
        tenant_id: str = Depends(authenticate),
    ) -> MemoryExplanation:
        memory = repository.get(tenant_id=tenant_id, agent_id=agent_id, memory_id=memory_id)
        if memory is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        matched_terms = _matched_terms(memory.content, query) if query else []
        now = datetime.now(UTC)
        return MemoryExplanation(
            memory_id=memory.id,
            type=memory.type,
            version=memory.version,
            status=_memory_status(memory, now),
            retrieval=RetrievalExplanation(
                strategy="lexical_fts5_bm25",
                matched_terms=matched_terms,
                filters_applied=["tenant_id", "agent_id", "expires_at"],
            ),
        )

    return app


app = create_app()


def _memory_status(memory: MemoryRecord, now: datetime) -> str:
    return "expired" if memory.expires_at is not None and memory.expires_at <= now else "active"


def _to_memory_response(memory: MemoryRecord, now: datetime) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        agent_id=memory.agent_id,
        content=memory.content,
        type=memory.type,
        version=memory.version,
        status=_memory_status(memory, now),
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        expires_at=memory.expires_at,
        metadata=memory.metadata,
    )


def _matched_terms(content: str, query: str) -> list[str]:
    content_terms = {term.lower() for term in re.findall(r"[\w]+", content, flags=re.UNICODE)}
    return [
        term
        for term in re.findall(r"[\w]+", query, flags=re.UNICODE)
        if term.lower() in content_terms
    ]
