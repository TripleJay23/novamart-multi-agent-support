from typing import Any

import pytest

from novamart_support.config import Settings
from novamart_support.exceptions import ConfigurationError
from novamart_support.repositories import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)
from novamart_support.runtime import build_application
from novamart_support.services import (
    InventoryService,
    PolicyService,
    RefundService,
)
from novamart_support.state import DynamoDBWorkflowStateRepository


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

    container = build_application(
        settings,
        dynamodb_client=object(),
        bedrock_runtime_client=bedrock_client,
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
    assert isinstance(container.inventory_service, InventoryService)
    assert isinstance(container.refund_service, RefundService)
    assert isinstance(container.policy_service, PolicyService)

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
