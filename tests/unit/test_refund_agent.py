from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import boto3
from strands.models import BedrockModel

from novamart_support.agents import (
    REFUND_SYSTEM_PROMPT,
    build_refund_agent,
    build_refund_tools,
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
from novamart_support.services import InventoryService, RefundService
from novamart_support.tools import RefundToolHandlers

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def build_handlers() -> RefundToolHandlers:
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
        quantity=2,
        status=OrderStatus.DELIVERED,
        ordered_at=NOW - timedelta(days=12),
        delivered_at=NOW - timedelta(days=10),
        return_eligible=True,
    )

    inventory = InventoryService(
        InMemoryCustomerRepository([customer]),
        InMemoryOrderRepository([order]),
    )

    refund = RefundService(
        inventory,
        clock=lambda: NOW,
    )

    return RefundToolHandlers(refund)


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


def test_refund_tool_has_expected_contract() -> None:
    tools = build_refund_tools(build_handlers())

    assert len(tools) == 1
    assert tools[0].tool_name == "evaluate_refund"
    assert tools[0].tool_spec


def test_refund_agent_registers_only_refund_tool() -> None:
    model = build_offline_model()

    agent = build_refund_agent(
        build_handlers(),
        build_settings(),
        model=model,
    )

    assert agent.name == "RefundAgent"
    assert agent.model is model

    assert set(agent.tool_registry.registry) == {
        "evaluate_refund",
    }


def test_refund_agent_prompt_enforces_deterministic_decision_boundary() -> None:
    prompt = REFUND_SYSTEM_PROMPT.casefold()

    assert "always use the refund eligibility tool" in prompt
    assert "do not override" in prompt
    assert "never invent" in prompt


def test_refund_agent_prompt_does_not_claim_processing_authority() -> None:
    prompt = REFUND_SYSTEM_PROMPT.casefold()

    assert "do not claim that a refund" in prompt
    assert "do not modify orders" in prompt
    assert "do not create the final customer-facing" in prompt


def test_refund_agent_constructs_worker_bedrock_model() -> None:
    injected_model = build_offline_model()
    settings = build_settings()

    with patch(
        "novamart_support.agents.refund.BedrockModel",
        return_value=injected_model,
    ) as model_factory:
        agent = build_refund_agent(
            build_handlers(),
            settings,
        )

    model_factory.assert_called_once_with(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    assert agent.model is injected_model
