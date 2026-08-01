"""A complete local DMA SDK example.

Start the API first with ``make api`` from the repository root. This example
never embeds secrets: set DMA_API_KEY in the environment before running it.
"""

from __future__ import annotations

import os

from dma import DMAClient, MemoryType


def main() -> None:
    with DMAClient(
        api_key=os.environ["DMA_API_KEY"],
        agent_id="my-coding-agent",
        base_url=os.getenv("DMA_BASE_URL", "http://127.0.0.1:8000"),
    ) as memory:
        stored = memory.remember(
            content="User prefers Java Spring Boot over Node for backend work.",
            type=MemoryType.SEMANTIC,
            metadata={"source": "basic-python-example"},
        )
        context = memory.recall(query="What backend stack does the user prefer?")

    print(f"Stored: {stored.id}")
    for result in context:
        print(f"[{result.score:.3f}] {result.content}")


if __name__ == "__main__":
    main()
