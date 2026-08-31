"""FastAPI application for DMA."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    status,
)

from dma_api.config import AuthLimits, Settings
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
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository, get_analyzer

logger = logging.getLogger("dma_api.auth")


@dataclass
class _SourceRecord:
    timestamps: list[float] = field(default_factory=list)
    locked_until: float = 0.0


class InMemoryRateLimiter:
    """Per-source sliding-window rate limiter with lockout for failed auth."""

    def __init__(self, limits: AuthLimits) -> None:
        self._max_attempts = limits.max_attempts
        self._window = limits.window_seconds
        self._lockout = limits.lockout_seconds
        self._max_sources = limits.max_tracked_sources
        self._sources: dict[str, _SourceRecord] = {}
        self._lock = threading.Lock()

    def is_locked_out(self, source: str) -> bool:
        with self._lock:
            record = self._sources.get(source)
            if record is None:
                return False
            return record.locked_until > time.monotonic()

    def record_failure(self, source: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._evict_stale(now)
            record = self._sources.setdefault(source, _SourceRecord())
            cutoff = now - self._window
            record.timestamps = [t for t in record.timestamps if t > cutoff]
            record.timestamps.append(now)
            if len(record.timestamps) >= self._max_attempts:
                record.locked_until = now + self._lockout
            attempts_in_window = len(record.timestamps)
        logger.warning(
            "auth_failure source=%s total_in_window=%d",
            source,
            attempts_in_window,
        )

    def record_success(self, source: str) -> None:
        with self._lock:
            self._sources.pop(source, None)

    def tracked_sources(self) -> int:
        with self._lock:
            return len(self._sources)

    def _evict_stale(self, now: float) -> None:
        """Drop sources without in-window failures or an active lockout.

        Must be called while holding ``self._lock``. When eviction alone cannot
        keep the map under ``max_tracked_sources``, the least recently active
        sources are dropped so source churn cannot grow memory without bound.
        """
        cutoff = now - self._window
        for key, record in list(self._sources.items()):
            if record.locked_until > now:
                continue
            if not any(timestamp > cutoff for timestamp in record.timestamps):
                del self._sources[key]
        overflow = len(self._sources) - self._max_sources + 1
        if overflow <= 0:
            return
        stalest = sorted(self._sources, key=self._last_activity)[:overflow]
        for key in stalest:
            del self._sources[key]

    def _last_activity(self, source: str) -> float:
        record = self._sources[source]
        return max(record.locked_until, max(record.timestamps, default=0.0))


def _client_source(
    request: Request, x_forwarded_for: str | None, *, trust_forwarded_for: bool
) -> str:
    """Identify the caller for rate limiting.

    ``X-Forwarded-For`` is honoured only when the deployment declares that it
    runs behind a trusted proxy; otherwise a client could rotate the header to
    win a fresh failure counter for every guess. The transport peer address is
    the default, so direct callers are never pooled into one shared bucket.
    """
    if trust_forwarded_for and x_forwarded_for:
        forwarded = x_forwarded_for.split(",")[0].strip()
        if forwarded:
            return forwarded
    client = request.client
    return client.host if client is not None else "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable API application."""
    runtime_settings = settings or Settings()
    analyzer = get_analyzer(runtime_settings.analyzer_kind)
    repository = SQLiteMemoryRepository(runtime_settings.database_path, analyzer=analyzer)
    rate_limiter = InMemoryRateLimiter(runtime_settings.auth_limits)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        repository.initialize()
        yield

    app = FastAPI(title="DMA API", version="0.1.0", lifespan=lifespan)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    def authenticate(
        request: Request,
        authorization: str | None = Header(default=None),
        x_forwarded_for: str | None = Header(default=None, alias="X-Forwarded-For"),
    ) -> str:
        source = _client_source(
            request, x_forwarded_for, trust_forwarded_for=runtime_settings.trust_forwarded_for
        )
        if rate_limiter.is_locked_out(source):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="too many failed authentication attempts; try again later",
            )
        expected = f"Bearer {runtime_settings.api_key}"
        if authorization is None or not secrets.compare_digest(authorization, expected):
            rate_limiter.record_failure(source)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key"
            )
        rate_limiter.record_success(source)
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
    def forget(
        memory_id: str = Path(pattern=r"^mem_[A-Za-z0-9]+$"),
        agent_id: str = Query(min_length=1, max_length=128),
        tenant_id: str = Depends(authenticate),
    ) -> Response:
        if not repository.delete(tenant_id=tenant_id, agent_id=agent_id, memory_id=memory_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="memory not found")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/v1/memories/{memory_id}/explanation", response_model=MemoryExplanation)
    def explain(
        memory_id: str = Path(pattern=r"^mem_[A-Za-z0-9]+$"),
        agent_id: str = Query(min_length=1, max_length=128),
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


app = create_app(Settings.from_env())


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
