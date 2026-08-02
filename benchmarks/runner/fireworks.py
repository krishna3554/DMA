"""Opt-in Fireworks classifier used only by the evaluation harness."""
from __future__ import annotations

import json
from dataclasses import dataclass
from time import perf_counter

import httpx
from dma_api.models import MemoryType

BASE_URL = "https://api.fireworks.ai/inference/v1"

@dataclass(frozen=True, slots=True)
class Classification:
    type: MemoryType
    latency_ms: float
    model: str

class FireworksClassifier:
    def __init__(self, *, api_key: str, model: str, transport: httpx.BaseTransport | None = None) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("api_key and model must not be blank")
        self.model = model
        self.client = httpx.Client(base_url=BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=30, transport=transport)

    def classify(self, content: str) -> Classification:
        started = perf_counter()
        response = self.client.post("/chat/completions", json={
            "model": self.model,
            "temperature": 0,
            "max_tokens": 30,
            "messages": [{"role": "system", "content": "Classify memory as episodic, semantic, or procedural. Return only JSON."}, {"role": "user", "content": content}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "memory_type", "schema": {"type": "object", "properties": {"type": {"type": "string", "enum": ["episodic", "semantic", "procedural"]}}, "required": ["type"], "additionalProperties": False}}},
        })
        response.raise_for_status()
        payload = json.loads(response.json()["choices"][0]["message"]["content"])
        return Classification(MemoryType(payload["type"]), (perf_counter() - started) * 1000, self.model)
