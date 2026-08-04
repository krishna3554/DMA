API_PYTHON := services/dma-api/.venv/bin/python
API_PYTEST := services/dma-api/.venv/bin/pytest
API_RUFF := services/dma-api/.venv/bin/ruff
API_PYRIGHT := services/dma-api/.venv/bin/pyright

.PHONY: api example benchmark build test lint typecheck check

api:
	DMA_DATABASE_PATH=.local/dma.db DMA_API_KEY=$${DMA_API_KEY:-dma-local-development-key} $(API_PYTHON) -m uvicorn dma_api.main:app --host 127.0.0.1 --port 8000 --reload

example:
	DMA_API_KEY=$${DMA_API_KEY:-dma-local-development-key} $(API_PYTHON) examples/basic-python/main.py

benchmark:
	$(API_PYTHON) -m benchmarks.runner.benchmark

classify-benchmark:
	$(API_PYTHON) -m benchmarks.runner.classification

build:
	uv build packages/dma-sdk-python
	uv build packages/dma-langgraph
	uv build packages/dma-mcp

test:
	PYTHONPATH=. $(API_PYTEST) -q services/dma-api/tests packages/dma-sdk-python/tests benchmarks/runner/tests
	PYTHONPATH=.:packages/dma-mcp/src $(API_PYTEST) -q packages/dma-langgraph/tests packages/dma-mcp/tests

lint:
	$(API_RUFF) check services/dma-api/src services/dma-api/tests packages/dma-sdk-python/src packages/dma-sdk-python/tests packages/dma-langgraph packages/dma-mcp benchmarks

typecheck:
	cd services/dma-api && .venv/bin/pyright
	cd packages/dma-sdk-python && ../../services/dma-api/.venv/bin/pyright
	cd packages/dma-langgraph && ../../services/dma-api/.venv/bin/pyright
	cd benchmarks && ../services/dma-api/.venv/bin/pyright

check: test lint typecheck
