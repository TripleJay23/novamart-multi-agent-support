from unittest.mock import patch

import boto3
from strands.models import BedrockModel

from novamart_support.agents import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    build_orchestrator_agent,
    build_orchestrator_tools,
)
from novamart_support.config import Settings
from novamart_support.services.workflow import (
    INVENTORY_AGENT,
    REFUND_AGENT,
    WorkflowService,
)
from novamart_support.state import InMemoryWorkflowStateRepository
from novamart_support.tools import OrchestratorToolHandlers


def build_service() -> WorkflowService:
    return WorkflowService(
        InMemoryWorkflowStateRepository()
    )


def build_handlers() -> OrchestratorToolHandlers:
    return OrchestratorToolHandlers(
        build_service()
    )


def build_offline_model() -> BedrockModel:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        region_name="us-east-1",
    )

    return BedrockModel(
        boto_session=session,
        model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    )


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        AWS_REGION="us-east-1",
        ORCHESTRATOR_MODEL_ID=(
            "us.anthropic.claude-haiku-4-5-20251001-v1:0"
        ),
    )


def test_start_workflow_returns_deterministic_first_agent() -> None:
    handlers = build_handlers()

    response = handlers.start_workflow(
        " session-001 ",
        " Can I return order ORD-001? ",
        "return_refund",
        customer_id=" CUST-001 ",
    )

    assert response["ok"] is True

    data = response["data"]

    assert data["session_id"] == "session-001"
    assert data["customer_id"] == "CUST-001"
    assert data["request_type"] == "return_refund"
    assert data["status"] == "active"
    assert data["route_history"] == []
    assert data["next_agent"] == INVENTORY_AGENT


def test_start_workflow_rejects_unknown_classification() -> None:
    handlers = build_handlers()

    response = handlers.start_workflow(
        "session-001",
        "Please help me.",
        "something_else",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_request_type"


def test_start_workflow_returns_controlled_duplicate_error() -> None:
    service = build_service()
    handlers = OrchestratorToolHandlers(service)

    first = handlers.start_workflow(
        "session-001",
        "Where is my order?",
        "order",
    )
    second = handlers.start_workflow(
        "session-001",
        "Where is my order?",
        "order",
    )

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"]["code"] == "workflow_already_exists"


def test_get_next_agent_reflects_persisted_workflow_progress() -> None:
    service = build_service()
    handlers = OrchestratorToolHandlers(service)

    handlers.start_workflow(
        "session-001",
        "Can I return order ORD-001?",
        "return_refund",
        customer_id="CUST-001",
    )

    service.record_inventory_context(
        "session-001",
        {
            "order_id": "ORD-001",
            "status": "delivered",
        },
    )

    response = handlers.get_next_agent(
        "session-001"
    )

    assert response["ok"] is True
    assert response["data"]["route_history"] == [
        INVENTORY_AGENT,
    ]
    assert response["data"]["next_agent"] == REFUND_AGENT


def test_get_next_agent_returns_controlled_missing_workflow_error() -> None:
    handlers = build_handlers()

    response = handlers.get_next_agent(
        "missing-session"
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "workflow_not_found"


def test_orchestrator_tools_have_expected_contract() -> None:
    tools = build_orchestrator_tools(
        build_handlers()
    )

    assert [
        item.tool_name
        for item in tools
    ] == [
        "start_workflow",
        "get_next_agent",
    ]

    for item in tools:
        assert item.tool_spec


def test_orchestrator_agent_registers_only_workflow_controls() -> None:
    model = build_offline_model()

    agent = build_orchestrator_agent(
        build_handlers(),
        build_settings(),
        model=model,
    )

    assert agent.name == "OrchestratorAgent"
    assert agent.model is model

    assert set(agent.tool_registry.registry) == {
        "start_workflow",
        "get_next_agent",
    }


def test_orchestrator_prompt_enforces_classification_and_routing_boundary() -> None:
    prompt = ORCHESTRATOR_SYSTEM_PROMPT.casefold()

    assert "choose exactly one request type" in prompt
    assert "treat next_agent" in prompt
    assert "never invent, reorder, skip, or override" in prompt
    assert "deterministic workflow service" in prompt


def test_orchestrator_prompt_blocks_business_and_final_response_authority() -> None:
    prompt = ORCHESTRATOR_SYSTEM_PROMPT.casefold()

    assert "never make refund eligibility" in prompt
    assert "never invent customer or order facts" in prompt
    assert "do not produce the final customer-facing answer" in prompt


def test_orchestrator_agent_constructs_orchestrator_bedrock_model() -> None:
    injected_model = build_offline_model()
    settings = build_settings()

    with patch(
        "novamart_support.agents.orchestrator.BedrockModel",
        return_value=injected_model,
    ) as model_factory:
        agent = build_orchestrator_agent(
            build_handlers(),
            settings,
        )

    model_factory.assert_called_once_with(
        model_id=settings.orchestrator_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
    )

    assert agent.model is injected_model
