from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import boto3
from strands.models import BedrockModel

from novamart_support.agents import (
    INVENTORY_SYSTEM_PROMPT,
    build_inventory_agent,
    build_inventory_tools,
)
from novamart_support.config import Settings
from novamart_support.domain import (
    Customer,
    CustomerTier,
    Order,
    OrderStatus,
)
from novamart_support.repositories import (
    InMemoryCustomerRepository,
    InMemoryOrderRepository,
)
from novamart_support.services import InventoryService
from novamart_support.tools import InventoryToolHandlers

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def build_handlers() -> InventoryToolHandlers:
    customer = Customer(
        customer_id="CUST-001",
        name="Alex Customer",
        tier=CustomerTier.PREMIUM,
        email="alex@example.test",
    )

    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        product_name="Wireless Headphones Pro",
        category="Electronics",
        unit_price=Decimal("149.99"),
        quantity=1,
        status=OrderStatus.DELIVERED,
        ordered_at=NOW,
        delivered_at=NOW,
        return_eligible=True,
    )

    service = InventoryService(
        InMemoryCustomerRepository([customer]),
        InMemoryOrderRepository([order]),
    )

    return InventoryToolHandlers(service)


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


def test_inventory_tools_have_expected_names() -> None:
    tools = build_inventory_tools(build_handlers())

    assert [item.tool_name for item in tools] == [
        "get_customer_profile",
        "get_order",
        "list_customer_orders",
    ]


def test_inventory_tools_have_input_schemas() -> None:
    tools = build_inventory_tools(build_handlers())

    specifications = {
        item.tool_name: item.tool_spec
        for item in tools
    }

    assert set(specifications) == {
        "get_customer_profile",
        "get_order",
        "list_customer_orders",
    }

    for specification in specifications.values():
        assert specification


def test_inventory_agent_registers_only_inventory_tools() -> None:
    model = build_offline_model()

    agent = build_inventory_agent(
        build_handlers(),
        build_settings(),
        model=model,
    )

    assert agent.name == "InventoryAgent"
    assert agent.model is model

    assert set(agent.tool_registry.registry) == {
        "get_customer_profile",
        "get_order",
        "list_customer_orders",
    }


def test_inventory_agent_prompt_enforces_role_boundary() -> None:
    prompt = INVENTORY_SYSTEM_PROMPT.casefold()

    assert "never invent" in prompt
    assert "do not determine refund eligibility" in prompt
    assert "do not interpret" in prompt
    assert "do not create the final customer-facing" in prompt


def test_inventory_agent_constructs_worker_bedrock_model() -> None:
    injected_model = build_offline_model()
    settings = build_settings()

    with patch(
        "novamart_support.agents.inventory.BedrockModel",
        return_value=injected_model,
    ) as model_factory:
        agent = build_inventory_agent(
            build_handlers(),
            settings,
        )

    model_factory.assert_called_once_with(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    assert agent.model is injected_model
