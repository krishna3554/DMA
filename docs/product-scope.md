# DMA v0.1 product scope

## Outcome

Ship `dma-sdk`, a Python package that lets an agent developer persist and retrieve typed memories through a small, stable API.

```python
from dma import DMAClient

memory = DMAClient(api_key="...", agent_id="my-coding-agent")
memory.remember(
    content="User prefers Java Spring Boot for backend work.",
    type="semantic",
)
context = memory.recall(query="What backend stack does the user prefer?")
```

## In scope

- Tenant- and agent-scoped memories.
- Explicit `episodic`, `semantic`, and `procedural` types.
- `remember`, `recall`, `forget`, `list`, and `explain` SDK operations.
- A versioned HTTP API and OpenAPI specification.
- Deterministic full-text retrieval, lifecycle filters, and explanation payloads.
- SQLite for local development, with PostgreSQL migration support designed into the persistence interface.
- Idempotent writes, pagination, typed errors, test coverage, and an initial benchmark fixture.

## Explicitly out of scope

- Automatic LLM classification on the read/write path.
- LLM conflict resolution or summarisation.
- TypeScript SDK, browser client, hosted billing, or enterprise SSO.
- Vector search as a required dependency.
- Framework-specific logic in the core runtime.

## Why explicit types first

Explicit types prove the differentiated-memory model without relying on probabilistic model output. This makes behavior cheap, explainable, and benchmarkable. A classifier can become an opt-in server capability only after it beats this baseline on a tracked evaluation set.

## Non-negotiable engineering rules

- Every resource is scoped by authenticated tenant and `agent_id`.
- API URLs are versioned under `/v1`.
- Writes accept an idempotency key.
- No content is emitted in logs by default.
- Deletion semantics and retention must be documented and tested.
- Public request/response shapes are compatibility-tested against OpenAPI.
