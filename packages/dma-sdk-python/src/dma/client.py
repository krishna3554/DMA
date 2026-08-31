"""Synchronous Python client for the DMA HTTP API."""

from __future__ import annotations

import random
import time
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Self
from uuid import uuid4

import httpx

from dma.errors import AuthenticationError, DMAApiError, DMAConnectionError, ValidationError
from dma.models import (
    Memory,
    MemoryExplanation,
    MemoryPage,
    MemoryType,
    RecallResult,
    RetrievalExplanation,
)

_DEFAULT_BASE_URL = "https://api.dma.dev"
_DEFAULT_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = 0.2


class DMAClient:
    """A small, typed client for storing and recalling agent memory.

    The caller owns the client lifecycle. Use it as a context manager in scripts
    and services to ensure its HTTP connection pool is closed.

    Transport failures are retried up to ``max_retries`` times for requests that
    are safe to replay: reads, and writes carrying an ``Idempotency-Key``.
    Deletes are never retried.
    """

    def __init__(
        self,
        *,
        api_key: str,
        agent_id: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 5.0,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValidationError("api_key must not be blank")
        if not agent_id.strip():
            raise ValidationError("agent_id must not be blank")
        if timeout <= 0:
            raise ValidationError("timeout must be greater than zero")
        if max_retries < 0:
            raise ValidationError("max_retries must not be negative")
        self._agent_id = agent_id
        self._max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            headers={"Authorization": f"Bearer {api_key}", "User-Agent": "dma-sdk-python/0.1.0a0"},
            transport=transport,
        )

    def remember(
        self,
        *,
        content: str,
        type: MemoryType | str,
        metadata: Mapping[str, Any] | None = None,
        expires_at: datetime | None = None,
        idempotency_key: str | None = None,
    ) -> Memory:
        """Persist one typed memory and return its server-assigned record."""
        self._validate_non_blank(content, "content")
        memory_type = self._memory_type(type)
        key = idempotency_key or uuid4().hex
        if len(key) < 16:
            raise ValidationError("idempotency_key must contain at least 16 characters")
        payload: dict[str, Any] = {
            "agent_id": self._agent_id,
            "content": content,
            "type": memory_type.value,
            "metadata": dict(metadata or {}),
        }
        if expires_at is not None:
            payload["expires_at"] = expires_at.isoformat()
        response = self._request(
            "POST", "v1/memories", json=payload, headers={"Idempotency-Key": key}, retryable=True
        )
        return _memory_from_payload(response.json())

    def recall(
        self,
        *,
        query: str,
        types: list[MemoryType | str] | None = None,
        limit: int = 5,
    ) -> list[RecallResult]:
        """Return memories ranked by the server's retrieval policy."""
        self._validate_non_blank(query, "query")
        if not 1 <= limit <= 50:
            raise ValidationError("limit must be between 1 and 50")
        payload: dict[str, Any] = {"agent_id": self._agent_id, "query": query, "limit": limit}
        if types is not None:
            payload["types"] = [self._memory_type(memory_type).value for memory_type in types]
        response = self._request("POST", "v1/memories/recall", json=payload, retryable=True)
        return [_recall_result_from_payload(item) for item in response.json()["results"]]

    def list(
        self,
        *,
        type: MemoryType | str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> MemoryPage:
        """List this agent's memories using the API's stable cursor pagination."""
        if not 1 <= limit <= 100:
            raise ValidationError("limit must be between 1 and 100")
        params: dict[str, Any] = {"agent_id": self._agent_id, "limit": limit}
        if type is not None:
            params["type"] = self._memory_type(type).value
        if cursor is not None:
            params["cursor"] = cursor
        response = self._request("GET", "v1/memories", params=params, retryable=True)
        payload = response.json()
        return MemoryPage(
            items=[_memory_from_payload(item) for item in payload["items"]],
            next_cursor=payload["next_cursor"],
        )

    def forget(self, memory_id: str) -> None:
        """Hard-delete one memory owned by this client agent."""
        self._validate_non_blank(memory_id, "memory_id")
        self._request("DELETE", f"v1/memories/{memory_id}", params={"agent_id": self._agent_id})

    def explain(self, memory_id: str, *, query: str | None = None) -> MemoryExplanation:
        """Return the server's explainability metadata for a memory."""
        self._validate_non_blank(memory_id, "memory_id")
        if query is not None:
            self._validate_non_blank(query, "query")
        params: dict[str, Any] = {"agent_id": self._agent_id}
        if query is not None:
            params["query"] = query
        response = self._request(
            "GET", f"v1/memories/{memory_id}/explanation", params=params, retryable=True
        )
        payload = response.json()
        retrieval = payload["retrieval"]
        return MemoryExplanation(
            memory_id=payload["memory_id"],
            type=MemoryType(payload["type"]),
            version=payload["version"],
            status=payload["status"],
            retrieval=RetrievalExplanation(
                strategy=retrieval["strategy"],
                matched_terms=retrieval["matched_terms"],
                filters_applied=retrieval["filters_applied"],
            ),
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, method: str, path: str, *, retryable: bool = False, **kwargs: Any) -> httpx.Response:
        response = self._send(method, path, self._max_retries if retryable else 0, kwargs)
        if response.status_code == 401:
            raise AuthenticationError(401, "DMA API key was rejected")
        if response.is_error:
            message, code = _error_details(response)
            raise DMAApiError(response.status_code, message, code=code)
        return response

    def _send(self, method: str, path: str, retries: int, kwargs: dict[str, Any]) -> httpx.Response:
        for attempt in range(retries + 1):
            try:
                return self._client.request(method, path, **kwargs)
            except httpx.HTTPError as error:
                if attempt == retries:
                    raise DMAConnectionError("unable to reach the DMA API") from error
                time.sleep(_RETRY_BACKOFF_SECONDS * 2**attempt * (0.5 + random.random()))
        raise DMAConnectionError("unable to reach the DMA API")

    @staticmethod
    def _validate_non_blank(value: str, field: str) -> None:
        if not value or not value.strip():
            raise ValidationError(f"{field} must not be blank")

    @staticmethod
    def _memory_type(value: MemoryType | str) -> MemoryType:
        try:
            return MemoryType(value)
        except ValueError as error:
            allowed = ", ".join(memory_type.value for memory_type in MemoryType)
            raise ValidationError(f"type must be one of: {allowed}") from error


def _memory_from_payload(payload: Mapping[str, Any]) -> Memory:
    return Memory(
        id=payload["id"],
        agent_id=payload["agent_id"],
        content=payload["content"],
        type=MemoryType(payload["type"]),
        version=payload["version"],
        status=payload["status"],
        created_at=_parse_datetime(payload["created_at"]),
        updated_at=_parse_datetime(payload["updated_at"]),
        expires_at=_parse_datetime(payload["expires_at"]) if payload["expires_at"] else None,
        metadata=payload["metadata"],
    )


def _recall_result_from_payload(payload: Mapping[str, Any]) -> RecallResult:
    memory = _memory_from_payload(payload)
    return RecallResult(
        id=memory.id,
        agent_id=memory.agent_id,
        content=memory.content,
        type=memory.type,
        version=memory.version,
        status=memory.status,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        expires_at=memory.expires_at,
        metadata=memory.metadata,
        score=float(payload["score"]),
    )


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _error_details(response: httpx.Response) -> tuple[str, str | None]:
    try:
        payload = response.json()
    except ValueError:
        return f"DMA API request failed with status {response.status_code}", None
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("title")
        if isinstance(detail, str):
            return detail, payload.get("type") if isinstance(payload.get("type"), str) else None
    return f"DMA API request failed with status {response.status_code}", None
