from __future__ import annotations

from typing import Any

from dma import Memory, MemoryExplanation, RecallResult


class DMATools:
    """Structured DMA operations suitable for MCP tool registration."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def remember(self, content: str, type: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return _memory(self._memory.remember(content=content, type=type, metadata=metadata))

    def recall(self, query: str, types: list[str] | None = None, limit: int = 5) -> dict[str, Any]:
        results = self._memory.recall(query=query, types=types, limit=limit)
        return {"results": [_memory(result) | {"score": result.score} for result in results]}

    def forget(self, memory_id: str) -> dict[str, bool]:
        self._memory.forget(memory_id)
        return {"deleted": True}

    def explain(self, memory_id: str, query: str | None = None) -> dict[str, Any]:
        item: MemoryExplanation = self._memory.explain(memory_id, query=query)
        return {"memory_id": item.memory_id, "type": item.type.value, "version": item.version, "status": item.status, "retrieval": {"strategy": item.retrieval.strategy, "matched_terms": item.retrieval.matched_terms, "filters_applied": item.retrieval.filters_applied}}


def _memory(item: Memory | RecallResult) -> dict[str, Any]:
    return {"id": item.id, "agent_id": item.agent_id, "content": item.content, "type": item.type.value, "version": item.version, "status": item.status, "metadata": item.metadata}
