# DMA

DMA is a Python-first, framework-agnostic memory service for AI agents.

## Status

The repository is in its contract-first foundation phase. The first release is deliberately small: a Python SDK backed by a versioned HTTP API with typed `remember`, `recall`, `forget`, `list`, and `explain` operations.

See [product scope](docs/product-scope.md) and the [v1 API contract](openapi/dma-v1.yaml).

## Run locally

The repository uses one isolated local virtual environment at
`services/dma-api/.venv`. Install the service and SDK in editable mode, then
start the API:

```bash
uv venv services/dma-api/.venv --python python3
uv pip install --python services/dma-api/.venv/bin/python -e 'services/dma-api[dev]'
uv pip install --python services/dma-api/.venv/bin/python -e 'packages/dma-sdk-python[dev]'
make api
```

In a second terminal, run the complete SDK flow:

```bash
export DMA_API_KEY=dma-local-development-key
make example
```

For development verification, run `make check`.

### Local configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DMA_API_KEY` | `dma-local-development-key` | Local bearer token; replace outside development. |
| `DMA_TENANT_ID` | `local` | Tenant scope associated with the local API key. |
| `DMA_DATABASE_PATH` | `./dma.db` | SQLite database path. |
| `DMA_BASE_URL` | `http://127.0.0.1:8000` | API base URL used by the example. |

## Repository layout

- `packages/dma-sdk-python/` — developer-facing Python package
- `packages/dma-langgraph/` — thin LangGraph reference adapter
- `services/dma-api/` — hosted/self-hosted API service
- `openapi/` — versioned public contract
- `examples/` — runnable integrations
- `benchmarks/` — reproducible evaluation assets
- `docs/` — architecture and contributor documentation

## Principles

- The SDK is the product surface.
- Memory type is explicit in v0.1.
- Retrieval and lifecycle behavior must be explainable.
- Runtime dependencies must not require an LLM by default.
