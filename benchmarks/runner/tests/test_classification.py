from pathlib import Path

from benchmarks.runner.classification import evaluate


def test_rule_baseline_scores_perfectly_on_smoke_fixture() -> None:
    report = evaluate(Path("benchmarks/datasets/classification-v0.1.jsonl"))
    assert report == {"cases": 6, "accuracy": 1.0, "provider": "rule-based"}
