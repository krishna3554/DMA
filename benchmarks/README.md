# DMA benchmark suite

The initial `v0.1` fixture measures deterministic lexical retrieval. It is a
baseline, not an external-quality claim: six small, hand-labelled cases are
designed to validate typed filtering, agent isolation, expiry, and ranking.

Run it from the repository root:

```bash
make benchmark
```

The JSON report includes:

- `recall_at_1` and `recall_at_3`: fraction of expected memories retrieved.
- `mrr`: rank quality for cases with an expected memory.
- `excluded_memory_retrieval_rate`: retrieval of a labelled wrong-scope or
  wrong-type record.
- `stale_memory_retrieval_rate`: retrieval of a labelled expired record.
- `latency_ms.p50` and `latency_ms.p95`: repository retrieval latency only.

Do not compare latency across different machines. For quality comparisons,
keep the fixture version and retrieval limit fixed, record the implementation
version, and report all metrics rather than only the best one.
