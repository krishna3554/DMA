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
access to the host. Compose publishes the API on `127.0.0.1` only; expose it
deliberately (for example via a TLS proxy) if remote access is required. SQLite
is appropriate for a single self-hosted instance; PostgreSQL is the planned
multi-process deployment backend.

GitHub Actions runs this quality gate plus the offline benchmark baselines on
every pull request and on pushes to `main`.

## Use DMA with CLI agents

DMA can be used from CLI coding agents such as OpenCode, Claude Code, Hermes
Agent, or other local agent runners when the tool can do one of three things:

- run Python code that imports `dma-sdk`
- call the DMA HTTP API directly
- launch an MCP server

The recommended v0.1 integration shape is:

```text
CLI agent -> dma-mcp or small wrapper -> dma-sdk -> self-hosted DMA API -> SQLite
```

Use a stable `agent_id` per tool so memories stay scoped and benchmarks can
compare behavior by agent:

```text
opencode-agent
claude-code-agent
hermes-agent
```

### Option 1: Python SDK

Install the SDK into the environment used by the CLI tool or wrapper. The
packages are not published to PyPI yet; until the first release, build and
install them from a checkout:

```bash
make build
python -m pip install packages/dma-sdk-python/dist/dma_sdk-0.1.0a0-py3-none-any.whl
```

Use the same API key and base URL as your self-hosted server:

```python
from dma import DMAClient

memory = DMAClient(
    api_key="the-secret-from-your-env-file",
    agent_id="claude-code-agent",
    base_url="http://localhost:8000",
)

memory.remember(
    content="User prefers Java Spring Boot for backend APIs",
    type="semantic",
)

context = memory.recall("what backend stack does the user prefer?")
```

This path is useful for custom wrappers around OpenCode, Hermes Agent, or any
agent runner that lets you add Python hooks.

### Option 2: Direct HTTP

Any CLI tool that can call shell commands can use the DMA API directly:

```bash
curl -X POST http://localhost:8000/v1/memories/recall \
  -H "Authorization: Bearer the-secret-from-your-env-file" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "opencode-agent",
    "query": "what backend stack does the user prefer?",
    "limit": 3
  }'
```

This path is simple for early experiments, but SDK or MCP integration usually
gives better ergonomics.

### Option 3: MCP server

For tools that support MCP servers, install `dma-mcp`. Like the SDK, it is not
on PyPI yet; build it from a checkout first:

```bash
make build
python -m pip install packages/dma-mcp/dist/dma_mcp-0.1.0a0-py3-none-any.whl
```

Configure the tool to launch:

```bash
dma-mcp
```

with environment variables:

```bash
DMA_API_KEY=the-secret-from-your-env-file
DMA_BASE_URL=http://localhost:8000
DMA_MCP_AGENT_ID=claude-code-agent
```

Use this path for Claude Code-style integrations because MCP is designed for
tool and memory servers. Each external agent should get its own
`DMA_MCP_AGENT_ID` unless you intentionally want shared memory.

For real-world evaluation, run the same project twice: once without DMA and
once with DMA enabled. Compare preference adherence, repeated corrections,
irrelevant recalls, useful recalls, task completion time, and added latency.

## Build distributable packages

Before publishing a release, build the Python distributions locally:

```bash
make build
```

This produces source distributions and wheels for `dma-sdk`, `dma-langgraph`,
and `dma-mcp` in each package's `dist/` directory. Publication to PyPI remains
an explicit release action; v0.1 does not publish automatically from CI.

Run `make verify-wheels` to install the built artifacts into a fresh temporary
environment. The container publishing target for v0.1 is GitHub Container
Registry (GHCR). See `docs/releasing.md` for the TestPyPI, PyPI, and GHCR
release workflow.

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
