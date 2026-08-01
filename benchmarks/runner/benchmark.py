"""Run the versioned DMA retrieval benchmark without external services."""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from dma_api.models import MemoryType
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository

_TENANT_ID = "benchmark-tenant"
_DEFAULT_NOW = datetime.fromisoformat("2026-08-01T00:00:00+00:00")


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    result_ids: list[str]
    expected_ids: list[str]
    excluded_ids: list[str]
    stale_ids: list[str]
    elapsed_ms: float


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    """Load newline-delimited benchmark cases, rejecting malformed fixtures."""
    cases = [json.loads(line) for line in dataset_path.read_text().splitlines() if line.strip()]
    if not cases:
        raise ValueError("benchmark dataset is empty")
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("benchmark case IDs must be unique")
    return cases


def run_benchmark(dataset_path: Path, *, limit: int = 3) -> dict[str, Any]:
    """Execute each case in an isolated SQLite database and calculate metrics."""
    cases = load_cases(dataset_path)
    with tempfile.TemporaryDirectory(prefix="dma-benchmark-") as directory:
        results = [
            _run_case(case, Path(directory) / f"{case['case_id']}.db", limit=limit)
            for case in cases
        ]
    return _summarise(results, dataset_path, limit)


def _run_case(case: dict[str, Any], database_path: Path, *, limit: int) -> CaseResult:
    repository = SQLiteMemoryRepository(database_path)
    repository.initialize()
    for index, memory in enumerate(case["memories"]):
        timestamp = _DEFAULT_NOW.replace(microsecond=index)
        expires_at = datetime.fromisoformat(memory["expires_at"]) if "expires_at" in memory else None
        record = MemoryRecord(
            id=memory["id"],
            tenant_id=_TENANT_ID,
            agent_id=memory["agent_id"],
            content=memory["content"],
            type=MemoryType(memory["type"]),
            version=1,
            created_at=timestamp,
            updated_at=timestamp,
            expires_at=expires_at,
            metadata={},
        )
        repository.create_or_get(record, f"benchmark-{case['case_id']}-{index:04d}")

    types = [MemoryType(value) for value in case["types"]] if "types" in case else None
    started = perf_counter_ns()
    matches = repository.recall(
        tenant_id=_TENANT_ID,
        agent_id="coding-agent",
        query=case["query"],
        types=types,
        limit=limit,
        now=_DEFAULT_NOW,
    )
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    return CaseResult(
        case_id=case["case_id"],
        result_ids=[memory.id for memory, _ in matches],
        expected_ids=case["expected_memory_ids"],
        excluded_ids=case.get("excluded_memory_ids", []),
        stale_ids=case.get("stale_memory_ids", []),
        elapsed_ms=elapsed_ms,
    )


def _summarise(results: list[CaseResult], dataset_path: Path, limit: int) -> dict[str, Any]:
    relevant = [result for result in results if result.expected_ids]
    recall_at_1 = _mean(_recall_at(result, 1) for result in relevant)
    recall_at_limit = _mean(_recall_at(result, limit) for result in relevant)
    mrr = _mean(_reciprocal_rank(result) for result in relevant)
    retrieved_ids = [memory_id for result in results for memory_id in result.result_ids]
    excluded_ids = {memory_id for result in results for memory_id in result.excluded_ids}
    stale_ids = {memory_id for result in results for memory_id in result.stale_ids}
    return {
        "dataset": dataset_path.name,
        "cases": len(results),
        "retrieval_limit": limit,
        "metrics": {
            "recall_at_1": recall_at_1,
            f"recall_at_{limit}": recall_at_limit,
            "mrr": mrr,
            "excluded_memory_retrieval_rate": _rate(retrieved_ids, excluded_ids),
            "stale_memory_retrieval_rate": _rate(retrieved_ids, stale_ids),
            "latency_ms": {
                "p50": _percentile([result.elapsed_ms for result in results], 50),
                "p95": _percentile([result.elapsed_ms for result in results], 95),
            },
        },
        "cases_detail": [
            {
                "case_id": result.case_id,
                "result_ids": result.result_ids,
                "expected_ids": result.expected_ids,
                "elapsed_ms": result.elapsed_ms,
            }
            for result in results
        ],
    }


def _recall_at(result: CaseResult, k: int) -> float:
    return len(set(result.result_ids[:k]).intersection(result.expected_ids)) / len(result.expected_ids)


def _reciprocal_rank(result: CaseResult) -> float:
    expected = set(result.expected_ids)
    for rank, memory_id in enumerate(result.result_ids, start=1):
        if memory_id in expected:
            return 1 / rank
    return 0.0


def _mean(values: Any) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _rate(retrieved_ids: list[str], labelled_ids: set[str]) -> float:
    return sum(memory_id in labelled_ids for memory_id in retrieved_ids) / len(retrieved_ids) if retrieved_ids else 0.0


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[percentile - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DMA lexical retrieval benchmark.")
    parser.add_argument("--dataset", type=Path, default=Path("benchmarks/datasets/v0.1.jsonl"))
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if not 1 <= arguments.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    report = run_benchmark(arguments.dataset, limit=arguments.limit)
    output = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output + "\n")
    print(output)


if __name__ == "__main__":
    main()
