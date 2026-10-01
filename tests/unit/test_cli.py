from typing import Any

import pytest

from novamart_support import cli
from novamart_support.domain import (
    RequestType,
    WorkflowState,
    WorkflowStatus,
)
from novamart_support.exceptions import AgentExecutionError


class FakeRuntime:
    def __init__(
        self,
        *,
        run_state: WorkflowState | Exception,
        resume_state: WorkflowState | Exception | None = None,
    ) -> None:
        self.run_state = run_state
        self.resume_state = (
            resume_state
            if resume_state is not None
            else run_state
        )
        self.run_calls: list[dict[str, Any]] = []
        self.resume_calls: list[str] = []

    def run(
        self,
        session_id: str,
        original_query: str,
        *,
        customer_id: str | None = None,
    ) -> WorkflowState:
        self.run_calls.append(
            {
                "session_id": session_id,
                "original_query": original_query,
                "customer_id": customer_id,
            }
        )

        if isinstance(self.run_state, Exception):
            raise self.run_state

        return self.run_state

    def resume(
        self,
        session_id: str,
    ) -> WorkflowState:
        self.resume_calls.append(session_id)

        if isinstance(self.resume_state, Exception):
            raise self.resume_state

        return self.resume_state


class FakeApplication:
    def __init__(
        self,
        runtime: FakeRuntime,
    ) -> None:
        self.runtime = runtime


def completed_state() -> WorkflowState:
    return WorkflowState(
        session_id="session-001",
        customer_id="CUST-001",
        original_query="Where is my order?",
        request_type=RequestType.ORDER,
        status=WorkflowStatus.COMPLETED,
        route_history=[
            "InventoryAgent",
            "CommunicationAgent",
        ],
        final_response="Your order has shipped.",
        version=2,
    )


def install_fake_application(
    monkeypatch: pytest.MonkeyPatch,
    runtime: FakeRuntime,
) -> None:
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: object(),
    )
    monkeypatch.setattr(
        cli,
        "build_application",
        lambda settings: FakeApplication(runtime),
    )


def test_run_executes_new_workflow_and_prints_final_response(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = FakeRuntime(
        run_state=completed_state()
    )
    install_fake_application(
        monkeypatch,
        runtime,
    )

    exit_code = cli.main(
        [
            "run",
            "--session-id",
            "session-001",
            "--query",
            "Where is my order?",
            "--customer-id",
            "CUST-001",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "Your order has shipped."
    assert captured.err == ""

    assert runtime.run_calls == [
        {
            "session_id": "session-001",
            "original_query": "Where is my order?",
            "customer_id": "CUST-001",
        }
    ]


def test_json_output_exposes_safe_workflow_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = FakeRuntime(
        run_state=completed_state()
    )
    install_fake_application(
        monkeypatch,
        runtime,
    )

    exit_code = cli.main(
        [
            "run",
            "--session-id",
            "session-001",
            "--query",
            "Where is my order?",
            "--json",
        ]
    )

    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"session_id": "session-001"' in output
    assert '"status": "completed"' in output
    assert '"final_response": "Your order has shipped."' in output

    assert "inventory_context" not in output
    assert "policy_context" not in output
    assert "refund_context" not in output


def test_resume_uses_existing_workflow(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = FakeRuntime(
        run_state=completed_state()
    )
    install_fake_application(
        monkeypatch,
        runtime,
    )

    exit_code = cli.main(
        [
            "resume",
            "--session-id",
            "session-001",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert runtime.run_calls == []
    assert runtime.resume_calls == [
        "session-001"
    ]
    assert captured.out.strip() == "Your order has shipped."


def test_failed_terminal_workflow_returns_nonzero_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failed = WorkflowState(
        session_id="session-failed",
        original_query="Help.",
        request_type=RequestType.GENERAL,
        status=WorkflowStatus.FAILED,
        version=1,
    )

    runtime = FakeRuntime(
        run_state=failed
    )
    install_fake_application(
        monkeypatch,
        runtime,
    )

    exit_code = cli.main(
        [
            "resume",
            "--session-id",
            "session-failed",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert (
        "status=failed"
        in captured.out
    )


def test_controlled_runtime_error_is_written_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = FakeRuntime(
        run_state=AgentExecutionError(
            "Agent execution failed."
        )
    )
    install_fake_application(
        monkeypatch,
        runtime,
    )

    exit_code = cli.main(
        [
            "run",
            "--session-id",
            "session-001",
            "--query",
            "Help.",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert captured.err.strip() == (
        "error: Agent execution failed."
    )
