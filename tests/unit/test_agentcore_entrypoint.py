from types import SimpleNamespace

import pytest
from bedrock_agentcore.runtime import RequestContext
from starlette.testclient import TestClient

from novamart_support import agentcore
from novamart_support.domain import RequestType, WorkflowState, WorkflowStatus
from novamart_support.exceptions import (
    AgentExecutionError,
    ConcurrencyConflictError,
    ConfigurationError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)

SESSION = "00000000-0000-4000-8000-000000000001"


class FakeRuntime:
    def __init__(self, *, status=WorkflowStatus.COMPLETED, error=None):
        self.error = error
        self.calls = []
        self.state = WorkflowState(
            session_id=SESSION,
            original_query="Where is my order?",
            request_type=RequestType.ORDER,
            status=status,
            inventory_context={"private": "internal-only"},
            route_history=["InventoryAgent", "CommunicationAgent"],
            final_response="Your order has shipped.",
            version=2,
        )

    def run(self, session_id, query, *, customer_id=None):
        self.calls.append(("run", session_id, query, customer_id))
        if self.error:
            raise self.error
        return self.state

    def resume(self, session_id):
        self.calls.append(("resume", session_id))
        if self.error:
            raise self.error
        return self.state


def install(monkeypatch, runtime):
    monkeypatch.setattr(agentcore, "get_settings", lambda: object())
    monkeypatch.setattr(
        agentcore, "build_application", lambda settings: SimpleNamespace(runtime=runtime),
    )


def test_run_uses_only_context_session_and_excludes_private_context(monkeypatch):
    runtime = FakeRuntime()
    install(monkeypatch, runtime)
    result = agentcore.handle_invocation(
        {"query": " Where is my order? ", "customer_id": "CUST-1001"},
        RequestContext(session_id=SESSION),
    )
    assert result["ok"] is True
    assert result["workflow"]["status"] == "completed"
    assert "inventory_context" not in result["workflow"]
    assert "internal-only" not in str(result)
    assert runtime.calls == [("run", SESSION, "Where is my order?", "CUST-1001")]


def test_resume_continues_only_the_context_session(monkeypatch):
    runtime = FakeRuntime()
    install(monkeypatch, runtime)
    result = agentcore.handle_invocation(
        {"action": "resume"}, RequestContext(session_id=SESSION),
    )
    assert result["ok"] is True
    assert runtime.calls == [("resume", SESSION)]


@pytest.mark.parametrize("payload", [
    {}, {"query": " "}, {"query": 42}, {"query": "x" * 10001},
    {"action": "unknown", "query": "hello"},
    {"action": "resume", "query": None},
    {"action": "resume", "customer_id": "CUST-1001"},
    {"query": "hello", "session_id": "another-session"},
])
def test_invalid_payload_cannot_construct_aws_application(monkeypatch, payload):
    monkeypatch.setattr(agentcore, "build_application", lambda _: pytest.fail("must not construct"))
    result = agentcore.handle_invocation(payload, RequestContext(session_id=SESSION))
    assert result["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("session_id", [None, "", "short", " " * 36, "x" * 257])
def test_missing_or_invalid_session_never_falls_back_to_a_shared_key(monkeypatch, session_id):
    monkeypatch.setattr(agentcore, "build_application", lambda _: pytest.fail("must not construct"))
    result = agentcore.handle_invocation({"query": "hello"}, RequestContext(session_id=session_id))
    assert result["error"]["code"] == "invalid_request"


@pytest.mark.parametrize(("error", "code"), [
    (ConfigurationError("private infrastructure"), "configuration_error"),
    (WorkflowNotFoundError("private session"), "workflow_not_found"),
    (WorkflowAlreadyExistsError("private session"), "workflow_exists"),
    (ConcurrencyConflictError("private state"), "conflict"),
    (AgentExecutionError("private prompt"), "execution_failed"),
    (RuntimeError("private AWS details"), "internal_error"),
])
def test_errors_return_stable_codes_without_raw_exception_content(monkeypatch, caplog, error, code):
    install(monkeypatch, FakeRuntime(error=error))
    result = agentcore.handle_invocation({"query": "hello"}, RequestContext(session_id=SESSION))
    assert result["ok"] is False
    assert result["error"]["code"] == code
    assert "private" not in str(result)
    assert "private" not in caplog.text


def test_terminal_failed_workflow_is_not_reported_as_success(monkeypatch):
    install(monkeypatch, FakeRuntime(status=WorkflowStatus.FAILED))
    result = agentcore.handle_invocation(
        {"action": "resume"}, RequestContext(session_id=SESSION),
    )
    assert result["ok"] is False
    assert result["workflow"]["status"] == "failed"


def test_each_invocation_builds_fresh_agents_even_in_a_warm_process(monkeypatch):
    created = []

    def factory(settings):
        runtime = FakeRuntime()
        created.append(runtime)
        return SimpleNamespace(runtime=runtime)

    monkeypatch.setattr(agentcore, "get_settings", lambda: object())
    monkeypatch.setattr(agentcore, "build_application", factory)
    for query in ("first customer", "second customer"):
        agentcore.handle_invocation({"query": query}, RequestContext(session_id=SESSION))
    assert len(created) == 2
    assert created[0] is not created[1]
    assert len(created[0].calls) == len(created[1].calls) == 1


def test_sdk_http_contract_supports_health_and_invocation(monkeypatch):
    runtime = FakeRuntime()
    install(monkeypatch, runtime)
    with TestClient(agentcore.app) as client:
        assert client.get("/ping").status_code == 200
        response = client.post(
            "/invocations", json={"query": "Where is my order?"},
            headers={"X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": SESSION},
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert runtime.calls[0][1] == SESSION
