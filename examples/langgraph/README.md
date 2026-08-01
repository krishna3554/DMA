# LangGraph adapter example

Install the adapter and LangGraph in your application environment:

```bash
pip install dma-sdk dma-langgraph 'dma-langgraph[langgraph]'
```

Start a DMA server, set `DMA_API_KEY`, then run `main.py`. The `recall_memory`
node adds `dma_context` and `dma_memories` to graph state before the response
node executes. Save only application-approved facts with `adapter.remember(...)`
after your response or review step.
