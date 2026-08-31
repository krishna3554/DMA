"""Use DMA as a retrieval node in a LangGraph StateGraph.

Start the API first with ``make api`` from the repository root, and install the
optional framework dependency: ``pip install 'dma-langgraph[langgraph]'``.
"""

from __future__ import annotations

import os
from typing import TypedDict

from dma import DMAClient
from dma_langgraph import DMAMemoryAdapter
from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict):
    user_input: str
    dma_context: str
    response: str


def respond(state: AgentState) -> dict[str, str]:
    # Replace this deterministic placeholder with your model invocation.
    return {"response": f"Relevant memory:\n{state['dma_context']}"}


def main() -> None:
    with DMAClient(
        api_key=os.environ["DMA_API_KEY"],
        agent_id="langgraph-agent",
        base_url=os.getenv("DMA_BASE_URL", "http://127.0.0.1:8000"),
    ) as memory:
        adapter = DMAMemoryAdapter(memory=memory, query_builder=lambda state: state["user_input"])
        builder = StateGraph(AgentState)
        builder.add_node("recall_memory", adapter.recall_node)
        builder.add_node("respond", respond)
        builder.add_edge(START, "recall_memory")
        builder.add_edge("recall_memory", "respond")
        builder.add_edge("respond", END)
        graph = builder.compile()
        result = graph.invoke({"user_input": "What backend does the user prefer?"})

    print(result["response"])


if __name__ == "__main__":
    main()
