# DMA

DMA is a Python-first, framework-agnostic memory service for AI agents.

## Status

The repository is in its contract-first foundation phase. The first release is deliberately small: a Python SDK backed by a versioned HTTP API with typed `remember`, `recall`, `forget`, `list`, and `explain` operations.

See [product scope](docs/product-scope.md) and the [v1 API contract](openapi/dma-v1.yaml).

## Repository layout

- `packages/dma-sdk-python/` — developer-facing Python package
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
