"""Thin state-node adapter for adding DMA memory to LangGraph workflows."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from dma import Memory, MemoryType, RecallResult, ValidationError


class MemoryClient(Protocol):
    """The portion of the DMA SDK used by this adapter."""

    def recall(
        self, *, query: str, types: list[MemoryType | str] | None = None, limit: int = 5
    ) -> list[RecallResult]: ...

    def remember(
        self,
        *,
        content: str,
        type: MemoryType | str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Memory: ...


QueryBuilder = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True, slots=True)
class DMAMemoryAdapter:
    """Build state-node functions that retrieve memory before an LLM node.

    The adapter deliberately does not infer what should be remembered. Call
    :meth:`remember` from an application-approved post-response step instead.
    """

    memory: MemoryClient
    query_builder: QueryBuilder
    context_key: str = "dma_context"
    results_key: str = "dma_memories"
    limit: int = 5
    types: list[MemoryType | str] | None = None

    def __post_init__(self) -> None:
        if not self.context_key.strip() or not self.results_key.strip():
            raise ValidationError("context_key and results_key must not be blank")
        if not 1 <= self.limit <= 50:
            raise ValidationError("limit must be between 1 and 50")

    def recall_node(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Return a LangGraph-compatible partial state update with DMA context."""
        query = self.query_builder(state)
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("query_builder must return a non-blank string")
        results = self.memory.recall(query=query, types=self.types, limit=self.limit)
        return {
            self.context_key: self.format_context(results),
            self.results_key: results,
        }

    def remember(
        self,
        *,
        content: str,
        type: MemoryType | str,
        metadata: Mapping[str, Any] | None = None,
    ) -> Memory:
        """Persist an application-selected memory after a graph step completes."""
        return self.memory.remember(content=content, type=type, metadata=metadata)

    @staticmethod
    def format_context(results: list[RecallResult]) -> str:
        """Format retrieved memory for direct insertion into an LLM prompt/state."""
        if not results:
            return ""
        return "\n".join(
            f"- [{result.type.value}; relevance={result.score:.2f}] {result.content}"
            for result in results
        )
