# Changelog

All notable DMA changes are recorded here. This project follows Semantic
Versioning and uses pre-release identifiers before the first stable release.

## [Unreleased]

### Added

- Release-build preflight and CI packaging checks.

### Fixed

- Scope idempotency keys to `(tenant_id, agent_id)`: existing databases are
  migrated on startup (the owning agent is backfilled from the linked memory
  and orphaned rows whose memory is gone are dropped), so two agents reusing
  the same key no longer resolve to each other's memory. The migration is safe
  to re-run.
- Enforce `DMA_MAX_REQUEST_BYTES` on the bytes actually read, so bodies
  without a `Content-Length` header (for example chunked transfer encoding)
  can no longer bypass the 413 limit.

## [0.1.0a0] - 2026-08-04

### Added

- Self-hosted DMA API with typed memory, lexical retrieval, lifecycle handling,
  and explainability.
- Python SDK, LangGraph adapter, and MCP adapter foundations.
- Docker Compose deployment, benchmark suite, and CI quality gates.
