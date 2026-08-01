"""Use DMA as a retrieval node in a LangGraph StateGraph.

Install the optional framework dependency first:
``pip install 'dma-langgraph[langgraph]'``.
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


memory = DMAClient(api_key=os.environ["DMA_API_KEY"], agent_id="langgraph-agent")
adapter = DMAMemoryAdapter(memory=memory, query_builder=lambda state: state["user_input"])


def respond(state: AgentState) -> dict[str, str]:
    # Replace this deterministic placeholder with your model invocation.
    return {"response": f"Relevant memory:\n{state['dma_context']}"}


builder = StateGraph(AgentState)
builder.add_node("recall_memory", adapter.recall_node)
builder.add_node("respond", respond)
builder.add_edge(START, "recall_memory")
builder.add_edge("recall_memory", "respond")
builder.add_edge("respond", END)
graph = builder.compile()

result = graph.invoke({"user_input": "What backend does the user prefer?"})
print(result["response"])
