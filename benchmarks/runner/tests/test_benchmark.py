from __future__ import annotations

from pathlib import Path

from benchmarks.runner.benchmark import run_benchmark


def test_v01_fixture_has_perfect_baseline_retrieval() -> None:
    report = run_benchmark(Path("benchmarks/datasets/v0.1.jsonl"))

    metrics = report["metrics"]
    assert report["cases"] == 6
    assert metrics["recall_at_1"] == 1.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["excluded_memory_retrieval_rate"] == 0.0
    assert metrics["stale_memory_retrieval_rate"] == 0.0
