#!/usr/bin/env bash
set -euo pipefail

verify_dir="$(mktemp -d)"
trap 'rm -rf "$verify_dir"' EXIT

uv venv "$verify_dir" --python python3
wheel_python="$verify_dir/bin/python"
uv pip install --python "$wheel_python" packages/dma-sdk-python/dist/*.whl
uv pip install --python "$wheel_python" --no-deps packages/dma-langgraph/dist/*.whl packages/dma-mcp/dist/*.whl
"$wheel_python" -c "from dma import DMAClient; from dma_langgraph import DMAMemoryAdapter; from dma_mcp import DMATools; print('wheel imports passed')"
