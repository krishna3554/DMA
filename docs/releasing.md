# Releasing DMA

This document describes the manual release flow for the v0.1 self-hosted DMA packages.

Release artifacts:

- Python packages: `dma-sdk`, `dma-langgraph`, `dma-mcp`
- Docker image: `ghcr.io/krishna3554/dma`

## Current version

The first alpha release is `0.1.0a0`.

PyPI and TestPyPI versions are immutable. If a bad package is uploaded, do not reuse the same version. Fix the issue, bump to the next alpha such as `0.1.0a1`, and publish again.

## One-time setup

Create GitHub environments:

- `testpypi-dma-sdk`
- `testpypi-dma-langgraph`
- `testpypi-dma-mcp`
- `pypi-dma-sdk`
- `pypi-dma-langgraph`
- `pypi-dma-mcp`

Recommended protection:

- TestPyPI environments: no approval required
- PyPI environments: require manual approval

Configure trusted publishing for each project on TestPyPI:

| Project name | Owner | Repository | Workflow filename | Environment |
| --- | --- | --- | --- | --- |
| `dma-sdk` | `krishna3554` | `DMA` | `release-python.yml` | `testpypi-dma-sdk` |
| `dma-langgraph` | `krishna3554` | `DMA` | `release-python.yml` | `testpypi-dma-langgraph` |
| `dma-mcp` | `krishna3554` | `DMA` | `release-python.yml` | `testpypi-dma-mcp` |

Configure the same trusted publishers on PyPI:

| Project name | Owner | Repository | Workflow filename | Environment |
| --- | --- | --- | --- | --- |
| `dma-sdk` | `krishna3554` | `DMA` | `release-python.yml` | `pypi-dma-sdk` |
| `dma-langgraph` | `krishna3554` | `DMA` | `release-python.yml` | `pypi-dma-langgraph` |
| `dma-mcp` | `krishna3554` | `DMA` | `release-python.yml` | `pypi-dma-mcp` |

If a project does not exist yet, create a pending publisher for that exact package name.

PyPI does not allow the same pending publisher identity to create multiple new
project names. The package-specific environment names above keep each pending
publisher unique.

## Publish to TestPyPI

In GitHub Actions, run `Release Python Packages` manually:

- `target`: `testpypi`

The workflow builds all package distributions, installs the generated wheels in a fresh environment, and publishes the validated distributions to TestPyPI.

## Verify TestPyPI

Run the self-hosted API:

```bash
DMA_API_KEY=local-dev-key docker compose up --build
```

In another terminal, install from TestPyPI in a clean environment:

```bash
release_tmp="$(mktemp -d)"
cd "$release_tmp"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ \
  dma-sdk==0.1.0a0
```

Run a quickstart smoke test:

```bash
python - <<'PY'
from dma import DMAClient

memory = DMAClient(
    api_key="local-dev-key",
    agent_id="release-smoke-test",
    base_url="http://127.0.0.1:8000",
)

stored = memory.remember(
    content="User prefers Java Spring Boot for backend work",
    type="semantic",
)
results = memory.recall("what backend stack does the user prefer?")

assert stored.id
assert results
assert "Spring Boot" in results[0].content
print("TestPyPI quickstart passed")
PY
```

Stop the API:

```bash
docker compose down
```

## Publish to PyPI

Only publish to PyPI after the TestPyPI package has been installed and verified from a clean environment.

In GitHub Actions, run `Release Python Packages` manually:

- `target`: `pypi`

Approve the `pypi` environment deployment if GitHub asks for approval.

Verify the final package from PyPI:

```bash
release_tmp="$(mktemp -d)"
cd "$release_tmp"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install dma-sdk==0.1.0a0
python - <<'PY'
from dma import DMAClient

print(DMAClient)
print("PyPI install passed")
PY
```

## Publish Docker Image

In GitHub Actions, run `Release Docker Image` manually:

- `version`: `0.1.0a0`
- `latest`: `false` for alpha releases, unless you intentionally want alpha users pulling `latest`

The expected image is:

```bash
ghcr.io/krishna3554/dma:0.1.0a0
```

Verify the published image:

```bash
docker pull ghcr.io/krishna3554/dma:0.1.0a0
docker run --rm \
  -e DMA_API_KEY=local-dev-key \
  -e DMA_ENVIRONMENT=production \
  -p 8000:8000 \
  ghcr.io/krishna3554/dma:0.1.0a0
```

In another terminal:

```bash
curl --fail http://127.0.0.1:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

After the first GHCR publish, check the package settings in GitHub:

- Open the repository package page
- Confirm `krishna3554/DMA` has Actions access
- Set package visibility to public only if public unauthenticated pulls are desired
