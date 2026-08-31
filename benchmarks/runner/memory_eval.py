"""Run the generated DMA memory evaluation suite."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from dma_api.models import MemoryType
from dma_api.repository import MemoryRecord, SQLiteMemoryRepository, AnalyzerKind, get_analyzer

DEFAULT_DATASET = Path("benchmarks/datasets/memory-eval-v0.1.jsonl")
DEFAULT_NOW = datetime.fromisoformat("2026-08-01T00:00:00+00:00")
TENANT_ID = "memory-eval-tenant"
# Use DomainAnalyzer for benchmark parity with the evaluation corpus.
# The DomainAnalyzer includes DMA-specific query expansions that the
# eval dataset was designed for. The default PLAIN analyzer has no
# expansions and uses prefix-only matching to avoid false positives.
BENCHMARK_ANALYZER = get_analyzer(AnalyzerKind.DOMAIN)


@dataclass(frozen=True, slots=True)
class MemoryEvalResult:
    case_id: str
    category: str
    result_ids: list[str]
    expected_ids: list[str]
    excluded_ids: list[str]
    stale_ids: list[str]
    should_recall: bool
    elapsed_ms: float
    query: str


def load_cases(dataset_path: Path) -> list[dict[str, Any]]:
    cases = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    _validate_cases(cases)
    return cases


def run_memory_eval(dataset_path: Path = DEFAULT_DATASET, *, limit: int = 3) -> dict[str, Any]:
    cases = load_cases(dataset_path)
    with tempfile.TemporaryDirectory(prefix="dma-memory-eval-") as directory:
        results = [
            _run_case(case, Path(directory) / f"{case['case_id']}.db", limit=limit)
            for case in cases
        ]
    return _summarise(results, dataset_path, limit)


def load_failures(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def write_failures(report: dict[str, Any], output_path: Path) -> None:
    failures = report["failures"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for failure in failures:
            file.write(json.dumps(failure, sort_keys=True) + "\n")


def _failures_to_set(failures: list[dict[str, Any]]) -> set[str]:
    return {json.dumps(failure, sort_keys=True) for failure in failures}


def _run_case(case: dict[str, Any], database_path: Path, *, limit: int) -> MemoryEvalResult:
    repository = SQLiteMemoryRepository(database_path, analyzer=BENCHMARK_ANALYZER)
    repository.initialize()
    for index, memory in enumerate(case["memories"]):
        timestamp = DEFAULT_NOW.replace(microsecond=index)
        expires_at = datetime.fromisoformat(memory["expires_at"]) if "expires_at" in memory else None
        repository.create_or_get(
            MemoryRecord(
                id=memory["id"],
                tenant_id=TENANT_ID,
                agent_id=memory["agent_id"],
                content=memory["content"],
                type=MemoryType(memory["type"]),
                version=1,
                created_at=timestamp,
                updated_at=timestamp,
                expires_at=expires_at,
                metadata={},
            ),
            f"memory-eval-{case['case_id']}-{index:04d}",
        )

    types = [MemoryType(value) for value in case.get("types", [])] or None
    started = perf_counter_ns()
    matches = repository.recall(
        tenant_id=TENANT_ID,
        agent_id=case["agent_id"],
        query=case["query"],
        types=types,
        limit=limit,
        now=DEFAULT_NOW,
    )
    elapsed_ms = (perf_counter_ns() - started) / 1_000_000
    return MemoryEvalResult(
        case_id=case["case_id"],
        category=case["category"],
        result_ids=[memory.id for memory, _ in matches],
        expected_ids=case["expected_memory_ids"],
        excluded_ids=case.get("excluded_memory_ids", []),
        stale_ids=case.get("stale_memory_ids", []),
        should_recall=case["should_recall"],
        elapsed_ms=elapsed_ms,
        query=case["query"],
    )


def _summarise(results: list[MemoryEvalResult], dataset_path: Path, limit: int) -> dict[str, Any]:
    relevant = [result for result in results if result.should_recall]
    negative = [result for result in results if not result.should_recall]
    retrieved_ids = [memory_id for result in results for memory_id in result.result_ids]
    excluded_ids = {memory_id for result in results for memory_id in result.excluded_ids}
    stale_ids = {memory_id for result in results for memory_id in result.stale_ids}
    failures = [_failure(result) for result in results if _is_failure(result, limit)]
    failures = [failure for failure in failures if failure is not None]

    category_metrics = {}
    grouped: dict[str, list[MemoryEvalResult]] = defaultdict(list)
    for result in results:
        grouped[result.category].append(result)
    for category, category_results in sorted(grouped.items()):
        category_metrics[category] = _metrics_for(category_results, limit)

    return {
        "dataset": dataset_path.name,
        "cases": len(results),
        "retrieval_limit": limit,
        "metrics": {
            **_metrics_for(results, limit),
            "false_positive_rate": _mean(1.0 if result.result_ids else 0.0 for result in negative),
            "excluded_memory_retrieval_rate": _rate(retrieved_ids, excluded_ids),
            "stale_memory_retrieval_rate": _rate(retrieved_ids, stale_ids),
            "latency_ms": {
                "p50": _percentile([result.elapsed_ms for result in results], 50),
                "p95": _percentile([result.elapsed_ms for result in results], 95),
            },
            "answerable_cases": len(relevant),
            "negative_cases": len(negative),
        },
        "categories": category_metrics,
        "failures": failures,
    }


def _metrics_for(results: list[MemoryEvalResult], limit: int) -> dict[str, float | int]:
    relevant = [result for result in results if result.should_recall]
    return {
        "cases": len(results),
        "recall_at_1": _mean(_recall_at(result, 1) for result in relevant),
        f"recall_at_{limit}": _mean(_recall_at(result, limit) for result in relevant),
        "mrr": _mean(_reciprocal_rank(result) for result in relevant),
    }


def _is_failure(result: MemoryEvalResult, limit: int) -> bool:
    if result.should_recall and _recall_at(result, limit) < 1.0:
        return True
    if not result.should_recall and result.result_ids:
        return True
    if set(result.result_ids).intersection(result.excluded_ids):
        return True
    return bool(set(result.result_ids).intersection(result.stale_ids))


def _failure(result: MemoryEvalResult) -> dict[str, object] | None:
    return {
        "case_id": result.case_id,
        "category": result.category,
        "query": result.query,
        "expected_ids": result.expected_ids,
        "actual_result_ids": result.result_ids,
        "excluded_ids": result.excluded_ids,
        "stale_ids": result.stale_ids,
        "should_recall": result.should_recall,
    }


def _recall_at(result: MemoryEvalResult, k: int) -> float:
    if not result.expected_ids:
        return 0.0
    return len(set(result.result_ids[:k]).intersection(result.expected_ids)) / len(result.expected_ids)


def _reciprocal_rank(result: MemoryEvalResult) -> float:
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


def _validate_cases(cases: list[dict[str, Any]]) -> None:
    if not cases:
        raise ValueError("memory evaluation dataset is empty")
    case_ids = [case["case_id"] for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("memory evaluation case IDs must be unique")
    for case in cases:
        if not case.get("category"):
            raise ValueError(f"{case['case_id']} is missing category")
        if not case.get("agent_id"):
            raise ValueError(f"{case['case_id']} is missing agent_id")
        if not case.get("query"):
            raise ValueError(f"{case['case_id']} is missing query")
        memories = case.get("memories")
        if not isinstance(memories, list) or not memories:
            raise ValueError(f"{case['case_id']} must include memories")
        memory_ids = {memory["id"] for memory in memories}
        for key in ("expected_memory_ids", "excluded_memory_ids", "stale_memory_ids"):
            if not set(case.get(key, [])).issubset(memory_ids):
                raise ValueError(f"{case['case_id']} references unknown {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DMA memory evaluation suite.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--failures-output", type=Path)
    parser.add_argument("--baseline", type=Path, help="Baseline failures file to compare against")
    parser.add_argument("--fail", action="store_true", help="Exit with code 1 if failures differ from baseline")
    arguments = parser.parse_args()
    report = run_memory_eval(arguments.dataset, limit=arguments.limit)
    output = json.dumps(report, indent=2, sort_keys=True)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output + "\n", encoding="utf-8")
    if arguments.failures_output:
        write_failures(report, arguments.failures_output)
    if arguments.baseline:
        current_failures = _failures_to_set(report["failures"])
        baseline_failures = load_failures(arguments.baseline)
        if current_failures != baseline_failures:
            print("Benchmark failures differ from baseline!")
            print(f"New failures: {current_failures - baseline_failures}")
            print(f"Fixed failures: {baseline_failures - current_failures}")
            if arguments.fail:
                sys.exit(1)
        else:
            print("Benchmark failures match baseline")
    print(output)


if __name__ == "__main__":
    main()
