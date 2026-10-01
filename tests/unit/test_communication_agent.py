from unittest.mock import patch

import boto3
from strands.models import BedrockModel

from novamart_support.agents import (
    COMMUNICATION_SYSTEM_PROMPT,
    build_communication_agent,
    build_communication_tools,
)
from novamart_support.config import Settings
from novamart_support.domain import RequestType, WorkflowState
from novamart_support.state import InMemoryWorkflowStateRepository
from novamart_support.tools import CommunicationToolHandlers


def build_repository() -> InMemoryWorkflowStateRepository:
    repository = InMemoryWorkflowStateRepository()

    repository.create(
        WorkflowState(
            session_id="session-001",
            customer_id="CUST-001",
            original_query="Can I return order ORD-001?",
            request_type=RequestType.RETURN_REFUND,
            route_history=[
                "InventoryAgent",
                "RefundAgent",
            ],
            inventory_context={
                "order_id": "ORD-001",
                "status": "delivered",
                "tier": "premium",
            },
            refund_context={
                "eligible": True,
                "reason": "Order is within the applicable return window.",
                "refund_amount": "149.99",
            },
        )
    )

    return repository


def build_handlers() -> CommunicationToolHandlers:
    return CommunicationToolHandlers(build_repository())


def build_offline_model() -> BedrockModel:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        region_name="us-east-1",
    )

    return BedrockModel(
        boto_session=session,
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        AWS_REGION="us-east-1",
        WORKER_MODEL_ID="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


def test_communication_handler_returns_curated_workflow_context() -> None:
    handlers = build_handlers()

    response = handlers.get_workflow_context("session-001")

    assert response["ok"] is True

    data = response["data"]

    assert data["session_id"] == "session-001"
    assert data["customer_id"] == "CUST-001"
    assert data["request_type"] == "return_refund"
    assert data["inventory_context"]["order_id"] == "ORD-001"
    assert data["refund_context"]["eligible"] is True

    assert "version" not in data
    assert "created_at" not in data
    assert "updated_at" not in data
    assert "final_response" not in data


def test_communication_handler_returns_controlled_missing_workflow_error() -> None:
    handlers = build_handlers()

    response = handlers.get_workflow_context("session-404")

    assert response["ok"] is False
    assert response["error"]["code"] == "workflow_not_found"


def test_communication_tool_has_expected_contract() -> None:
    tools = build_communication_tools(build_handlers())

    assert len(tools) == 1
    assert tools[0].tool_name == "get_workflow_context"
    assert tools[0].tool_spec


def test_communication_agent_registers_only_context_tool() -> None:
    model = build_offline_model()

    agent = build_communication_agent(
        build_handlers(),
        build_settings(),
        model=model,
    )

    assert agent.name == "CommunicationAgent"
    assert agent.model is model

    assert set(agent.tool_registry.registry) == {
        "get_workflow_context",
    }


def test_communication_prompt_enforces_grounding_and_final_authority() -> None:
    prompt = COMMUNICATION_SYSTEM_PROMPT.casefold()

    assert "only specialist agent" in prompt
    assert "base the response only" in prompt
    assert "never invent" in prompt
    assert "do not make new refund" in prompt


def test_communication_prompt_hides_internal_system_details() -> None:
    prompt = COMMUNICATION_SYSTEM_PROMPT.casefold()

    assert "do not expose internal agent names" in prompt
    assert "knowledge-base identifiers" in prompt
    assert "internal reasoning" in prompt
    assert "do not modify workflow state" in prompt


def test_communication_agent_constructs_worker_bedrock_model() -> None:
    injected_model = build_offline_model()
    settings = build_settings()

    with patch(
        "novamart_support.agents.communication.BedrockModel",
        return_value=injected_model,
    ) as model_factory:
        agent = build_communication_agent(
            build_handlers(),
            settings,
        )

    model_factory.assert_called_once_with(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    assert agent.model is injected_model
