"""Validate fixtures or run a paid, live Bedrock CommunicationAgent evaluation.

These lexical checks are a small regression gate, not a semantic judge. Review
the captured answers and fixture facts before making broader quality claims.
"""

import argparse
import hashlib
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from strands.models import BedrockModel

from novamart_support.agents import COMMUNICATION_SYSTEM_PROMPT, build_communication_agent
from novamart_support.config import Settings
from novamart_support.domain import WorkflowState
from novamart_support.runtime.outputs import CommunicationAgentOutput
from novamart_support.state import InMemoryWorkflowStateRepository
from novamart_support.tools import CommunicationToolHandlers
from novamart_support.tools.result import ToolResponse

ROOT = Path(__file__).resolve().parents[1]


def load_dataset(path: Path) -> dict[str, Any]:
    dataset = json.loads(path.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Dataset needs non-empty cases with unique IDs.")
    for case in cases:
        WorkflowState.model_validate(case["workflow"])
        if not case.get("required_patterns"):
            raise ValueError("Each case needs positive content checks.")
        for key in ("required_patterns", "forbidden_patterns"):
            for pattern in case.get(key, {}).values():
                re.compile(pattern, re.IGNORECASE)
    return dataset


def assess_response(case: dict[str, Any], response: str, *, context_reads: int) -> dict[str, Any]:
    checks = {"non_empty_response": bool(response.strip()), "context_tool_used": context_reads > 0}
    for name, pattern in case["required_patterns"].items():
        checks["required:" + name] = bool(re.search(pattern, response, re.IGNORECASE))
    for name, pattern in case.get("forbidden_patterns", {}).items():
        checks["forbidden:" + name] = not bool(re.search(pattern, response, re.IGNORECASE))
    return {"passed": all(checks.values()), "checks": checks}


class RecordingHandlers(CommunicationToolHandlers):
    def __init__(self, repository: InMemoryWorkflowStateRepository, session_id: str) -> None:
        super().__init__(repository)
        self.session_id = session_id
        self.context_reads = 0

    def get_workflow_context(self, session_id: str) -> ToolResponse:
        result = super().get_workflow_context(session_id)
        if session_id == self.session_id and result["ok"]:
            self.context_reads += 1
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evals/communication-v1.json")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--validate-only", action="store_true", help="No AWS calls.")
    mode.add_argument("--live", action="store_true", help="Invoke the configured Bedrock model.")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "docs/evidence/communication-eval.json",
    )
    parser.add_argument(
        "--profile", help="Optional existing AWS profile; keys are never read here.",
    )
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    if args.validate_only:
        print(f"Validated {len(dataset['cases'])} cases in {dataset['version']}; no AWS calls.")
        return 0

    settings = Settings()
    aws_session = boto3.Session(profile_name=args.profile, region_name=settings.aws_region)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
    report: dict[str, Any] = {
        "captured_at_utc": datetime.now(UTC).isoformat(),
        "base_revision": revision,
        "source_state": "Working tree; prompt and dataset hashes identify this evaluation.",
        "dataset_version": dataset["version"],
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "prompt_sha256": hashlib.sha256(COMMUNICATION_SYSTEM_PROMPT.encode()).hexdigest(),
        "model_id": settings.worker_model_id,
        "region": settings.aws_region,
        "scope": dataset["scope"],
        "limits": dataset["limits"],
        "human_review": "pending",
        "cases": [],
        "ok": False,
    }

    def save() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    save()
    try:
        for case in dataset["cases"]:
            record: dict[str, Any] = {"id": case["id"], "passed": False}
            report["cases"].append(record)
            state = WorkflowState.model_validate(case["workflow"])
            repository = InMemoryWorkflowStateRepository()
            repository.create(state)
            handlers = RecordingHandlers(repository, state.session_id)
            model = BedrockModel(
                boto_session=aws_session, model_id=settings.worker_model_id, temperature=0.1,
            )
            agent = build_communication_agent(handlers, settings, model=model)
            start = time.monotonic()
            try:
                result = agent(
                    f"Compose the final support response for session {state.session_id}. "
                    "Use get_workflow_context before responding. Return the requested output.",
                    structured_output_model=CommunicationAgentOutput,
                )
                output = result.structured_output
                if not isinstance(output, CommunicationAgentOutput):
                    raise ValueError("Missing validated communication output.")
                record.update(assess_response(
                    case, output.final_response, context_reads=handlers.context_reads,
                ))
                record["response"] = output.final_response
                record["checks"]["fixture_unchanged"] = repository.get(state.session_id) == state
                record["passed"] = all(record["checks"].values())
            except Exception as exc:
                # Raw SDK errors can contain environment identifiers; keep them out of evidence.
                record["error_type"] = type(exc).__name__
            record["context_reads"] = handlers.context_reads
            record["elapsed_seconds"] = round(time.monotonic() - start, 3)
            save()
            print(f"{case['id']}: {'PASS' if record['passed'] else 'FAIL'}", flush=True)
        report["ok"] = len(report["cases"]) == len(dataset["cases"]) and all(
            case["passed"] for case in report["cases"]
        )
    finally:
        save()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
