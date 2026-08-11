"""Offline classifier evaluation; provider calls belong behind this interface."""
from __future__ import annotations

import json
import os
from pathlib import Path

from dma_api.models import MemoryType

from benchmarks.runner.fireworks import FireworksClassifier


def classify_rule_based(content: str) -> MemoryType:
    text = content.lower()
    if any(token in text for token in ("always", "run ", "deploy", "workflow", "by ")):
        return MemoryType.PROCEDURAL
    if any(token in text for token in ("yesterday", "last friday", "happened", "decided")):
        return MemoryType.EPISODIC
    return MemoryType.SEMANTIC


def evaluate(dataset: Path, classifier=None) -> dict[str, float | int | str]:
    rows = [json.loads(line) for line in dataset.read_text().splitlines() if line.strip()]
    if classifier is None:
        labels = [classify_rule_based(row["content"]).value for row in rows]
        return {"cases": len(rows), "accuracy": sum(label == row["expected_type"] for label, row in zip(labels, rows)) / len(rows), "provider": "rule-based"}
    predictions = [classifier.classify(row["content"]) for row in rows]
    report = {"cases": len(rows), "accuracy": sum(item.type.value == row["expected_type"] for item, row in zip(predictions, rows)) / len(rows), "provider": classifier.model}
    report["mean_latency_ms"] = sum(item.latency_ms for item in predictions) / len(predictions)
    return report

if __name__ == "__main__":
    model = os.getenv("FIREWORKS_MODEL")
    key = os.getenv("FIREWORKS_API_KEY")
    classifier = FireworksClassifier(api_key=key, model=model) if key and model else None
    print(json.dumps(evaluate(Path("benchmarks/datasets/classification-v0.1.jsonl"), classifier), indent=2))
