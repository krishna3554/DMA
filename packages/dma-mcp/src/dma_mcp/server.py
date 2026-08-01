from __future__ import annotations

import os

from dma import DMAClient
from dma_mcp.tools import DMATools


def create_server(tools: DMATools):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("DMA Memory", instructions="Explicit, typed, explainable agent memory.")

    @server.tool(name="dma_remember")
    def dma_remember(content: str, type: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
        return tools.remember(content, type, metadata)

    @server.tool(name="dma_recall")
    def dma_recall(query: str, types: list[str] | None = None, limit: int = 5) -> dict[str, object]:
        return tools.recall(query, types, limit)

    @server.tool(name="dma_forget")
    def dma_forget(memory_id: str) -> dict[str, bool]:
        return tools.forget(memory_id)

    @server.tool(name="dma_explain")
    def dma_explain(memory_id: str, query: str | None = None) -> dict[str, object]:
        return tools.explain(memory_id, query)

    return server


def main() -> None:
    api_key = os.environ.get("DMA_API_KEY")
    if not api_key:
        raise SystemExit("DMA_API_KEY must be set")
    client = DMAClient(api_key=api_key, agent_id=os.getenv("DMA_MCP_AGENT_ID", "mcp-agent"), base_url=os.getenv("DMA_BASE_URL", "http://127.0.0.1:8000"))
    create_server(DMATools(client)).run(transport="stdio")
