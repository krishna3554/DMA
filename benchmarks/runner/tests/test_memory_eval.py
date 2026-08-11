from __future__ import annotations

from pathlib import Path

from benchmarks.runner.generate_memory_eval import generate_cases, write_cases
from benchmarks.runner.memory_eval import load_cases, run_memory_eval


def test_generated_memory_eval_dataset_is_valid(tmp_path: Path) -> None:
    output = tmp_path / "memory-eval.jsonl"
    cases = generate_cases()
    write_cases(cases, output)

    loaded = load_cases(output)

    assert len(loaded) == 115
    assert {case["category"] for case in loaded} == {
        "agent_isolation",
        "conflict_update",
        "distractor",
        "episodic_event",
        "expiry",
        "negative_no_answer",
        "procedural_workflow",
        "semantic_preference",
    }


def test_generated_memory_eval_runs_and_reports_failures(tmp_path: Path) -> None:
    output = tmp_path / "memory-eval.jsonl"
    write_cases(generate_cases(), output)

    report = run_memory_eval(output)

    assert report["cases"] == 115
    assert report["metrics"]["answerable_cases"] == 105
    assert report["metrics"]["negative_cases"] == 10
    assert "semantic_preference" in report["categories"]
    assert "failures" in report
