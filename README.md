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

## Self-host with Docker

v0.1 is self-hosted. Docker Compose runs the API in production mode and stores
SQLite data in the persistent `dma-data` volume.

```bash
cp .env.example .env
# Edit .env and replace DMA_API_KEY with a long random secret.
docker compose up --build -d
curl http://localhost:8000/healthz
```

Connect an agent with the SDK:

```python
from dma import DMAClient

memory = DMAClient(
    api_key="the-secret-from-your-env-file",
    agent_id="coding-agent",
    base_url="http://localhost:8000",
)
```

For a public deployment, put the API behind HTTPS and restrict database-volume
access to the host. SQLite is appropriate for a single self-hosted instance;
PostgreSQL is the planned multi-process deployment backend.

GitHub Actions runs this quality gate plus the offline benchmark baselines on
every pull request and on pushes to `main`.

### Local configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DMA_API_KEY` | `dma-local-development-key` | Local bearer token; replace outside development. |
| `DMA_TENANT_ID` | `local` | Tenant scope associated with the local API key. |
| `DMA_DATABASE_PATH` | `./dma.db` | SQLite database path. |
| `DMA_ENVIRONMENT` | `development` | Set to `production` to reject the insecure default API key. |
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
