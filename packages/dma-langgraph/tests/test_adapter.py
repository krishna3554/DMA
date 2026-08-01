from __future__ import annotations

from datetime import UTC, datetime

import pytest
from dma import Memory, MemoryType, RecallResult, ValidationError

from dma_langgraph import DMAMemoryAdapter


class FakeMemoryClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.remembered: list[tuple[str, MemoryType | str]] = []

    def recall(self, *, query: str, types=None, limit: int = 5) -> list[RecallResult]:
        self.queries.append(query)
        now = datetime.now(UTC)
        return [
            RecallResult(
                id="mem_java",
                agent_id="coding-agent",
                content="User prefers Java Spring Boot.",
                type=MemoryType.SEMANTIC,
                version=1,
                status="active",
                created_at=now,
                updated_at=now,
                expires_at=None,
                metadata={},
                score=1.0,
            )
        ]

    def remember(self, *, content: str, type: MemoryType | str, metadata=None) -> Memory:
        self.remembered.append((content, type))
        now = datetime.now(UTC)
        return Memory(
            id="mem_saved",
            agent_id="coding-agent",
            content=content,
            type=MemoryType(type),
            version=1,
            status="active",
            created_at=now,
            updated_at=now,
            expires_at=None,
            metadata=dict(metadata or {}),
        )


def test_recall_node_returns_partial_state_update() -> None:
    client = FakeMemoryClient()
    adapter = DMAMemoryAdapter(memory=client, query_builder=lambda state: state["user_input"])

    update = adapter.recall_node({"user_input": "Which backend does the user prefer?"})

    assert client.queries == ["Which backend does the user prefer?"]
    assert update["dma_memories"][0].id == "mem_java"
    assert update["dma_context"] == "- [semantic; relevance=1.00] User prefers Java Spring Boot."


def test_remember_is_explicit_application_control() -> None:
    client = FakeMemoryClient()
    adapter = DMAMemoryAdapter(memory=client, query_builder=lambda _: "query")

    memory = adapter.remember(content="Always run tests before a PR.", type="procedural")

    assert memory.id == "mem_saved"
    assert client.remembered == [("Always run tests before a PR.", "procedural")]


def test_query_builder_must_return_text() -> None:
    adapter = DMAMemoryAdapter(memory=FakeMemoryClient(), query_builder=lambda _: " ")

    with pytest.raises(ValidationError, match="query_builder"):
        adapter.recall_node({})
