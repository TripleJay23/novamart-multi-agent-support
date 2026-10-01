from typing import Any

import boto3
import pytest
from strands import Agent
from strands.models import BedrockModel

from novamart_support.config import Settings
from novamart_support.exceptions import ConfigurationError
from novamart_support.repositories import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)
from novamart_support.runtime import (
    MultiAgentRuntime,
    build_application,
)
from novamart_support.services import (
    InventoryService,
    PolicyService,
    RefundService,
    WorkflowService,
)
from novamart_support.state import DynamoDBWorkflowStateRepository
from novamart_support.tools import (
    CommunicationToolHandlers,
    InventoryToolHandlers,
    OrchestratorToolHandlers,
    PolicyToolHandlers,
    RefundToolHandlers,
)


class FakeBedrockRuntimeClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)

        knowledge_base_id = kwargs["knowledgeBaseId"]

        return {
            "guardrailAction": "NONE",
            "retrievalResults": [
                {
                    "content": {
                        "type": "TEXT",
                        "text": f"Evidence from {knowledge_base_id}",
                    },
                    "documentId": f"{knowledge_base_id}-document",
                    "score": 0.9,
                }
            ],
        }


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "PROJECT_NAME": "novamart-test",
        "RETURNS_KB_ID": "RETURNSKB1",
        "SHIPPING_KB_ID": "SHIPPINGKB1",
        "WARRANTY_KB_ID": "WARRANTYKB1",
    }
    values.update(overrides)

    return Settings(
        _env_file=None,
        **values,
    )


def build_offline_model(
    model_id: str,
) -> BedrockModel:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        region_name="us-east-1",
    )

    return BedrockModel(
        boto_session=session,
        model_id=model_id,
    )


def test_table_names_default_from_project_name() -> None:
    settings = make_settings()

    assert (
        settings.resolved_workflow_table_name
        == "novamart-test-workflow-state"
    )
    assert settings.resolved_customer_table_name == "novamart-test-customers"
    assert settings.resolved_order_table_name == "novamart-test-orders"


def test_explicit_table_names_override_derived_names() -> None:
    settings = make_settings(
        WORKFLOW_TABLE_NAME="workflow-custom",
        CUSTOMER_TABLE_NAME="customers-custom",
        ORDER_TABLE_NAME="orders-custom",
    )

    assert settings.resolved_workflow_table_name == "workflow-custom"
    assert settings.resolved_customer_table_name == "customers-custom"
    assert settings.resolved_order_table_name == "orders-custom"


def test_missing_policy_configuration_is_rejected() -> None:
    settings = make_settings(
        RETURNS_KB_ID="",
    )

    with pytest.raises(
        ConfigurationError,
        match="RETURNS_KB_ID",
    ):
        build_application(
            settings,
            dynamodb_client=object(),
            bedrock_runtime_client=FakeBedrockRuntimeClient(),
        )


def test_incomplete_guardrail_configuration_is_rejected() -> None:
    settings = make_settings(
        GUARDRAIL_ID="guardrail-123",
        GUARDRAIL_VERSION="",
    )

    with pytest.raises(
        ConfigurationError,
        match="configured together",
    ):
        build_application(
            settings,
            dynamodb_client=object(),
            bedrock_runtime_client=FakeBedrockRuntimeClient(),
        )


def test_application_dependency_graph_is_constructed() -> None:
    bedrock_client = FakeBedrockRuntimeClient()

    settings = make_settings(
        GUARDRAIL_ID="guardrail-123",
        GUARDRAIL_VERSION="2",
    )

    orchestrator_model = build_offline_model(
        settings.orchestrator_model_id
    )
    worker_model = build_offline_model(
        settings.worker_model_id
    )

    container = build_application(
        settings,
        dynamodb_client=object(),
        bedrock_runtime_client=bedrock_client,
        orchestrator_model=orchestrator_model,
        worker_model=worker_model,
    )

    assert isinstance(
        container.workflow_repository,
        DynamoDBWorkflowStateRepository,
    )
    assert isinstance(
        container.customer_repository,
        DynamoDBCustomerRepository,
    )
    assert isinstance(
        container.order_repository,
        DynamoDBOrderRepository,
    )

    assert isinstance(
        container.inventory_service,
        InventoryService,
    )
    assert isinstance(
        container.refund_service,
        RefundService,
    )
    assert isinstance(
        container.policy_service,
        PolicyService,
    )
    assert isinstance(
        container.workflow_service,
        WorkflowService,
    )

    assert isinstance(
        container.inventory_handlers,
        InventoryToolHandlers,
    )
    assert isinstance(
        container.refund_handlers,
        RefundToolHandlers,
    )
    assert isinstance(
        container.policy_handlers,
        PolicyToolHandlers,
    )
    assert isinstance(
        container.communication_handlers,
        CommunicationToolHandlers,
    )
    assert isinstance(
        container.orchestrator_handlers,
        OrchestratorToolHandlers,
    )

    assert isinstance(container.inventory_agent, Agent)
    assert isinstance(container.refund_agent, Agent)
    assert isinstance(container.policy_agent, Agent)
    assert isinstance(container.communication_agent, Agent)
    assert isinstance(container.orchestrator_agent, Agent)

    assert container.inventory_agent.name == "InventoryAgent"
    assert container.refund_agent.name == "RefundAgent"
    assert container.policy_agent.name == "PolicyAgent"
    assert container.communication_agent.name == "CommunicationAgent"
    assert container.orchestrator_agent.name == "OrchestratorAgent"

    assert container.inventory_agent.model is worker_model
    assert container.refund_agent.model is worker_model
    assert container.policy_agent.model is worker_model
    assert container.communication_agent.model is worker_model
    assert container.orchestrator_agent.model is orchestrator_model

    assert isinstance(
        container.runtime,
        MultiAgentRuntime,
    )

    result = container.policy_service.search_all(
        "What policies apply?",
    )

    assert len(result.evidence) == 3
    assert result.failures == []

    assert {
        request["knowledgeBaseId"]
        for request in bedrock_client.requests
    } == {
        "RETURNSKB1",
        "SHIPPINGKB1",
        "WARRANTYKB1",
    }

    assert all(
        request["guardrailConfiguration"]
        == {
            "guardrailId": "guardrail-123",
            "guardrailVersion": "2",
        }
        for request in bedrock_client.requests
    )


def test_composed_agents_expose_only_their_bounded_tools() -> None:
    settings = make_settings()

    container = build_application(
        settings,
        dynamodb_client=object(),
        bedrock_runtime_client=FakeBedrockRuntimeClient(),
        orchestrator_model=build_offline_model(
            settings.orchestrator_model_id
        ),
        worker_model=build_offline_model(
            settings.worker_model_id
        ),
    )

    assert set(
        container.inventory_agent.tool_registry.registry
    ) == {
        "get_customer_profile",
        "get_order",
        "list_customer_orders",
    }

    assert set(
        container.refund_agent.tool_registry.registry
    ) == {
        "evaluate_refund",
    }

    assert set(
        container.policy_agent.tool_registry.registry
    ) == {
        "search_policies",
    }

    assert set(
        container.communication_agent.tool_registry.registry
    ) == {
        "get_workflow_context",
    }

    assert set(
        container.orchestrator_agent.tool_registry.registry
    ) == {
        "start_workflow",
        "get_next_agent",
    }
