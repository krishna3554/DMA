"""Generate the deterministic DMA memory evaluation dataset."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

MemoryType = Literal["episodic", "semantic", "procedural"]

DEFAULT_OUTPUT = Path("benchmarks/datasets/memory-eval-v0.1.jsonl")
DEFAULT_AGENT_ID = "coding-agent"
OTHER_AGENT_ID = "research-agent"


@dataclass(frozen=True, slots=True)
class MemoryFixture:
    content: str
    type: MemoryType
    agent_id: str = DEFAULT_AGENT_ID
    expires_at: str | None = None


def generate_cases() -> list[dict[str, object]]:
    """Generate stable benchmark cases that exercise DMA's v0.1 behavior."""
    cases: list[dict[str, object]] = []
    cases.extend(_semantic_preference_cases())
    cases.extend(_procedural_workflow_cases())
    cases.extend(_episodic_event_cases())
    cases.extend(_distractor_cases())
    cases.extend(_conflict_cases())
    cases.extend(_negative_cases())
    cases.extend(_agent_isolation_cases())
    cases.extend(_expiry_cases())
    _validate_cases(cases)
    return cases


def write_cases(cases: list[dict[str, object]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as file:
        for case in cases:
            file.write(json.dumps(case, sort_keys=True) + "\n")


def _semantic_preference_cases() -> list[dict[str, object]]:
    preferences = [
        ("backend stack", "Java Spring Boot over Node.js for backend APIs", "what backend stack does the user prefer?"),
        ("database", "PostgreSQL over MongoDB for production databases", "which database does the user prefer for production?"),
        ("frontend framework", "React with TypeScript for frontend work", "what frontend framework does the user prefer?"),
        ("cloud", "AWS over GCP for production deployments", "which cloud provider does the user prefer?"),
        ("testing", "pytest for Python service tests", "what Python test framework does the user like?"),
        ("api style", "OpenAPI-first REST APIs", "what API design style should be used?"),
        ("package manager", "uv for Python dependency management", "which Python package manager does the user prefer?"),
        ("database migration", "Alembic for schema migrations", "what migration tool should be used?"),
        ("queue", "SQS for managed background queues", "what queue does the user prefer?"),
        ("observability", "structured JSON logs over plain text logs", "what logging format does the user prefer?"),
        ("docs", "short practical documentation with runnable examples", "what documentation style does the user prefer?"),
        ("deployment", "Docker Compose for local self-host testing", "how should local self-host testing be run?"),
        ("auth", "bearer API keys for the alpha release", "what auth should the alpha release use?"),
        ("language", "Python before TypeScript for the SDK", "which SDK language should be built first?"),
        ("storage", "SQLite for v0.1 self-hosted storage", "what storage should v0.1 use?"),
        ("memory input", "explicit memory types instead of automatic classification in v0.1", "how should memory type be set in v0.1?"),
        ("release registry", "GHCR for Docker image publishing", "where should Docker images be published?"),
        ("model spend", "offline deterministic benchmarks before Fireworks model calls", "how should model credits be protected?"),
        ("framework adapter", "LangGraph as the first framework adapter", "which framework adapter should come first?"),
        ("public release", "alpha packages published before cloud hosting", "what should ship before cloud hosting?"),
        ("tenant scope", "api_key for tenant scope and agent_id for agent scope", "how should client scope be represented?"),
        ("retrieval", "explainable lexical retrieval before vector retrieval", "what retrieval style should be used first?"),
        ("ci", "wheel install checks before publishing", "what package check should run before publishing?"),
        ("quality", "category-level benchmark reporting", "how should benchmark results be reported?"),
        ("cloud", "self-hosted v0.1 before DMA Cloud", "what release model should v0.1 use?"),
        ("server", "FastAPI for the self-hosted DMA API", "which API framework should DMA use?"),
        ("license", "Apache-2.0 for the repository and packages", "what license should the repo use?"),
        ("evaluation", "Recall@1 and Recall@3 as primary retrieval metrics", "what retrieval metrics matter most?"),
        ("cleanup", "forget should hard-delete memories in v0.1", "what should forget do in v0.1?"),
        ("conflicts", "newer explicit preferences should win over older preferences", "how should preference conflicts be handled?"),
    ]
    return [
        _case(
            case_id=f"semantic-{index:03d}",
            category="semantic_preference",
            memories=[MemoryFixture(f"User prefers {preference}.", "semantic")],
            query=query,
            expected_memory_indexes=[0],
        )
        for index, (_, preference, query) in enumerate(preferences, start=1)
    ]


def _procedural_workflow_cases() -> list[dict[str, object]]:
    workflows = [
        ("Before implementing an API, write or update the OpenAPI contract.", "what should happen before implementing an API?"),
        ("When releasing Python packages, publish to TestPyPI before PyPI.", "what should happen before publishing to PyPI?"),
        ("When debugging recall failures, inspect category-level benchmark failures first.", "how should recall failures be debugged?"),
        ("When adding an adapter, keep the SDK surface remember and recall first.", "what should adapter work preserve?"),
        ("When running Docker locally, set DMA_API_KEY in the environment.", "what env var is needed for local Docker?"),
        ("When using Fireworks, run a small held-out evaluation before spending credits broadly.", "how should Fireworks credits be used?"),
        ("When changing retrieval ranking, rerun memory-eval before committing.", "what should happen after changing retrieval ranking?"),
        ("When adding a memory, include an idempotency key for write safety.", "what should writes include for safety?"),
        ("When making release notes, document user-facing package changes first.", "what should release notes focus on first?"),
        ("When testing a published package, install from a clean virtual environment.", "how should a published package be verified?"),
        ("When using LangGraph, recall memory before the model node.", "where should LangGraph recall run?"),
        ("When storing procedural memory, write it as an instruction rather than a vague preference.", "how should procedural memories be written?"),
        ("When configuring PyPI trusted publishers, match the workflow environment exactly.", "what must PyPI trusted publishers match?"),
        ("When exposing MCP tools, keep network settings in environment variables.", "how should MCP server settings be configured?"),
        ("When documenting quickstarts, include both server and SDK commands.", "what should quickstarts include?"),
    ]
    return [
        _case(
            case_id=f"procedural-{index:03d}",
            category="procedural_workflow",
            memories=[MemoryFixture(workflow, "procedural")],
            query=query,
            expected_memory_indexes=[0],
            types=["procedural"],
        )
        for index, (workflow, query) in enumerate(workflows, start=1)
    ]


def _episodic_event_cases() -> list[dict[str, object]]:
    events = [
        ("On 2026-08-04, the DMA branch added a classification benchmark.", "what happened on 2026-08-04?"),
        ("On 2026-08-05, Docker self-hosting was validated locally.", "when was Docker self-hosting validated?"),
        ("On 2026-08-11, DMA packages were published to PyPI.", "what DMA release event happened on 2026-08-11?"),
        ("During release hardening, the wheel verifier was changed to use a temp directory.", "what changed during release hardening?"),
        ("The first GHCR image tag was ghcr.io/krishna3554/dma:0.1.0a0.", "what was the first GHCR image tag?"),
        ("The first PyPI alpha version was 0.1.0a0.", "what was the first PyPI alpha version?"),
        ("The TestPyPI attempt failed because publishers were configured on the wrong index.", "why did the TestPyPI attempt fail?"),
        ("The release workflow was fixed to upload package-specific artifacts.", "what release workflow fix was made?"),
        ("The Docker publish workflow completed in GitHub Actions.", "where did the Docker publish complete?"),
        ("The clean PyPI install verified DMAClient, DMAMemoryAdapter, and DMATools imports.", "what imports were verified after PyPI publishing?"),
    ]
    return [
        _case(
            case_id=f"episodic-{index:03d}",
            category="episodic_event",
            memories=[MemoryFixture(event, "episodic")],
            query=query,
            expected_memory_indexes=[0],
            types=["episodic"],
        )
        for index, (event, query) in enumerate(events, start=1)
    ]


def _distractor_cases() -> list[dict[str, object]]:
    specs = [
        ("User prefers Java Spring Boot for backend APIs.", "User prefers React for frontend UI.", "what frontend framework does the user prefer?", 1),
        ("User prefers PostgreSQL for production.", "User uses SQLite for local self-hosted v0.1.", "what storage should local v0.1 use?", 1),
        ("When publishing Docker images, use GHCR.", "When publishing Python packages, use PyPI.", "where should Python packages be published?", 1),
        ("The SDK exposes remember and recall.", "The API exposes healthz for Docker checks.", "what endpoint checks Docker health?", 1),
        ("User wants Python SDK first.", "User wants TypeScript later if demand exists.", "when should TypeScript be added?", 1),
        ("DMA Cloud is future work.", "v0.1 is self-hosted.", "what is the v0.1 hosting model?", 1),
        ("Use LangGraph as the first framework adapter.", "Use MCP as a second ecosystem adapter.", "what proves framework-agnostic support?", 1),
        ("Benchmark retrieval quality with Recall@1.", "Benchmark classifier quality with accuracy.", "what metric evaluates classification?", 1),
        ("Use API keys for auth.", "Use agent_id for memory scope.", "what identifies the agent scope?", 1),
        ("Use semantic memory for preferences.", "Use procedural memory for workflows.", "what memory type stores workflows?", 1),
        ("Use episodic memory for dated events.", "Use semantic memory for stable facts.", "what memory type stores stable facts?", 1),
        ("Run make check for quality gates.", "Run make memory-eval for retrieval quality.", "what command evaluates retrieval quality?", 1),
        ("Store SQLite data in a Docker volume.", "Put the API behind HTTPS for public deployments.", "what should protect public deployments?", 1),
        ("Use Fireworks for classifier experiments.", "Use deterministic fixtures for retrieval eval.", "what should retrieval eval use?", 1),
        ("PyPI versions are immutable.", "GHCR image visibility can be changed later.", "what cannot be overwritten after release?", 0),
        ("The SDK package is dma-sdk.", "The LangGraph package is dma-langgraph.", "what package contains the LangGraph adapter?", 1),
        ("The MCP package is dma-mcp.", "The API service package is dma-api.", "what package exposes MCP tools?", 0),
        ("Use OpenAPI for the public contract.", "Use README for quickstart documentation.", "where is the public API contract described?", 0),
        ("Recall should exclude expired memories.", "List should paginate memories.", "what should recall exclude?", 0),
        ("Forget removes a memory.", "Explain shows retrieval details.", "what admin call shows retrieval details?", 1),
    ]
    cases = []
    for index, (first, second, query, expected_index) in enumerate(specs, start=1):
        cases.append(
            _case(
                case_id=f"distractor-{index:03d}",
                category="distractor",
                memories=[MemoryFixture(first, "semantic"), MemoryFixture(second, "semantic")],
                query=query,
                expected_memory_indexes=[expected_index],
                excluded_memory_indexes=[0 if expected_index == 1 else 1],
            )
        )
    return cases


def _conflict_cases() -> list[dict[str, object]]:
    specs = [
        ("User preferred Django for backend APIs.", "User now prefers Java Spring Boot for backend APIs.", "what backend framework does the user prefer now?"),
        ("User preferred MongoDB for app data.", "User now prefers PostgreSQL for app data.", "what database does the user prefer now?"),
        ("User preferred cloud hosting for v0.1.", "User now wants self-hosted v0.1.", "what hosting model does user want now?"),
        ("User preferred TypeScript SDK first.", "User now wants Python SDK first.", "which SDK language should be first now?"),
        ("User preferred Docker Hub for images.", "User now prefers GHCR for images.", "where should Docker images go now?"),
        ("User preferred classifier-first memory routing.", "User now wants explicit memory types in v0.1.", "how should memory type work now?"),
        ("User preferred cloud API keys only.", "User now wants local self-host API keys.", "what API key setup does user want now?"),
        ("User preferred hidden benchmarks.", "User now wants reproducible public benchmark reports.", "what benchmark reporting does user want now?"),
        ("User preferred no adapters.", "User now wants LangGraph and MCP adapters.", "which adapters does user want now?"),
        ("User preferred manual release uploads.", "User now wants GitHub trusted publishing.", "how should packages be published now?"),
        ("User preferred full runtime first.", "User now wants thin SDK first.", "what should be built first now?"),
        ("User preferred vector retrieval first.", "User now wants explainable lexical retrieval first.", "what retrieval should be first now?"),
        ("User preferred Node.js examples.", "User now wants Python examples.", "what examples should come first now?"),
        ("User preferred no license file.", "User now wants Apache-2.0 LICENSE at repo root.", "what license file should the repo have now?"),
        ("User preferred no Docker release.", "User now wants GHCR Docker release.", "what Docker release target does user want now?"),
    ]
    return [
        _case(
            case_id=f"conflict-{index:03d}",
            category="conflict_update",
            memories=[MemoryFixture(old, "semantic"), MemoryFixture(new, "semantic")],
            query=query,
            expected_memory_indexes=[1],
            excluded_memory_indexes=[0],
        )
        for index, (old, new, query) in enumerate(specs, start=1)
    ]


def _negative_cases() -> list[dict[str, object]]:
    specs = [
        ("User prefers PostgreSQL for production databases.", "what is the user's favorite mobile game?"),
        ("User wants Python SDK first.", "what color should the dashboard use?"),
        ("Use GHCR for Docker images.", "what is the user's preferred lunch order?"),
        ("Recall should exclude expired memories.", "which city does the user live in?"),
        ("Use LangGraph as the first adapter.", "what is the user's favorite music genre?"),
        ("PyPI versions are immutable.", "what is the user's phone number?"),
        ("Use Docker Compose for local self-host testing.", "what is the user's preferred laptop brand?"),
        ("Use OpenAPI for API contracts.", "what is the user's birthday?"),
        ("Use Fireworks carefully to protect credits.", "what movie did the user watch yesterday?"),
        ("Use Apache-2.0 for repository licensing.", "what is the user's favorite sport?"),
    ]
    return [
        _case(
            case_id=f"negative-{index:03d}",
            category="negative_no_answer",
            memories=[MemoryFixture(memory, "semantic")],
            query=query,
            expected_memory_indexes=[],
        )
        for index, (memory, query) in enumerate(specs, start=1)
    ]


def _agent_isolation_cases() -> list[dict[str, object]]:
    specs = [
        ("Coding agent user prefers Java Spring Boot.", "Research agent user prefers literature reviews.", "what backend does the coding agent user prefer?"),
        ("Coding agent should run make check.", "Research agent should summarize papers.", "what should the coding agent run?"),
        ("Coding agent stores OpenAPI specs.", "Research agent stores citation notes.", "what does the coding agent store?"),
        ("Coding agent uses GHCR.", "Research agent uses Zotero.", "what registry does the coding agent use?"),
        ("Coding agent works on DMA SDK.", "Research agent works on benchmark papers.", "what project does the coding agent work on?"),
        ("Coding agent prefers Python.", "Research agent prefers LaTeX.", "what language does the coding agent prefer?"),
        ("Coding agent needs Docker Compose.", "Research agent needs PDF export.", "what tool does the coding agent need?"),
        ("Coding agent validates wheels.", "Research agent validates citations.", "what does the coding agent validate?"),
        ("Coding agent documents APIs.", "Research agent documents methodology.", "what does the coding agent document?"),
        ("Coding agent measures recall latency.", "Research agent measures annotation quality.", "what latency does the coding agent measure?"),
    ]
    return [
        _case(
            case_id=f"agent-isolation-{index:03d}",
            category="agent_isolation",
            memories=[
                MemoryFixture(coding, "semantic", DEFAULT_AGENT_ID),
                MemoryFixture(research, "semantic", OTHER_AGENT_ID),
            ],
            query=query,
            expected_memory_indexes=[0],
            excluded_memory_indexes=[1],
        )
        for index, (coding, research, query) in enumerate(specs, start=1)
    ]


def _expiry_cases() -> list[dict[str, object]]:
    specs = [
        ("Temporary branch token expires after release.", "Permanent release token is stored in environment.", "what token is permanent?"),
        ("Old incident note expired yesterday.", "Current incident note says PyPI publish succeeded.", "what is the current incident status?"),
        ("Expired preference says use Docker Hub.", "Active preference says use GHCR.", "where should images be published?"),
        ("Expired storage note says use memory-only DB.", "Active storage note says use SQLite.", "what storage is active?"),
        ("Expired model note says call Fireworks for every case.", "Active model note says use offline retrieval eval.", "how should retrieval eval run?"),
    ]
    return [
        _case(
            case_id=f"expiry-{index:03d}",
            category="expiry",
            memories=[
                MemoryFixture(expired, "semantic", expires_at="2026-07-01T00:00:00+00:00"),
                MemoryFixture(active, "semantic"),
            ],
            query=query,
            expected_memory_indexes=[1],
            stale_memory_indexes=[0],
        )
        for index, (expired, active, query) in enumerate(specs, start=1)
    ]


def _case(
    *,
    case_id: str,
    category: str,
    memories: list[MemoryFixture],
    query: str,
    expected_memory_indexes: list[int],
    excluded_memory_indexes: list[int] | None = None,
    stale_memory_indexes: list[int] | None = None,
    types: list[str] | None = None,
) -> dict[str, object]:
    memory_dicts = []
    memory_ids = []
    for index, memory in enumerate(memories, start=1):
        memory_id = f"{case_id}-mem-{index:02d}"
        memory_ids.append(memory_id)
        data: dict[str, object] = {
            "id": memory_id,
            "agent_id": memory.agent_id,
            "content": memory.content,
            "type": memory.type,
        }
        if memory.expires_at is not None:
            data["expires_at"] = memory.expires_at
        memory_dicts.append(data)

    return {
        "case_id": case_id,
        "category": category,
        "agent_id": DEFAULT_AGENT_ID,
        "memories": memory_dicts,
        "query": query,
        "expected_memory_ids": [memory_ids[index] for index in expected_memory_indexes],
        "excluded_memory_ids": [memory_ids[index] for index in excluded_memory_indexes or []],
        "stale_memory_ids": [memory_ids[index] for index in stale_memory_indexes or []],
        "should_recall": bool(expected_memory_indexes),
        **({"types": types} if types else {}),
    }


def _validate_cases(cases: list[dict[str, object]]) -> None:
    if not cases:
        raise ValueError("memory evaluation dataset is empty")
    case_ids = [str(case["case_id"]) for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("memory evaluation case IDs must be unique")

    categories = {
        "semantic_preference",
        "procedural_workflow",
        "episodic_event",
        "distractor",
        "conflict_update",
        "negative_no_answer",
        "agent_isolation",
        "expiry",
    }
    memory_types = {"episodic", "semantic", "procedural"}
    for case in cases:
        if case["category"] not in categories:
            raise ValueError(f"unknown category: {case['category']}")
        if not str(case["query"]).strip():
            raise ValueError(f"{case['case_id']} has an empty query")
        memories = case["memories"]
        if not isinstance(memories, list) or not memories:
            raise ValueError(f"{case['case_id']} must include at least one memory")
        memory_ids = {str(memory["id"]) for memory in memories}
        expected = set(_string_list(case["expected_memory_ids"], "expected_memory_ids"))
        excluded = set(_string_list(case["excluded_memory_ids"], "excluded_memory_ids"))
        stale = set(_string_list(case["stale_memory_ids"], "stale_memory_ids"))
        if not expected.issubset(memory_ids):
            raise ValueError(f"{case['case_id']} references unknown expected memories")
        if not excluded.issubset(memory_ids):
            raise ValueError(f"{case['case_id']} references unknown excluded memories")
        if not stale.issubset(memory_ids):
            raise ValueError(f"{case['case_id']} references unknown stale memories")
        if bool(expected) != bool(case["should_recall"]):
            raise ValueError(f"{case['case_id']} has inconsistent should_recall")
        for memory in memories:
            if memory["type"] not in memory_types:
                raise ValueError(f"{case['case_id']} has invalid memory type")


def _string_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the DMA memory evaluation dataset.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    cases = generate_cases()
    write_cases(cases, args.output)
    print(json.dumps({"output": str(args.output), "cases": len(cases)}, sort_keys=True))


if __name__ == "__main__":
    main()
