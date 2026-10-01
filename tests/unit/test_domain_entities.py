from datetime import UTC, datetime
from decimal import Decimal

from novamart_support.domain import (
    Customer,
    CustomerTier,
    Order,
    OrderStatus,
    PolicyEvidence,
    PolicyType,
    RefundDecision,
)


def test_customer_defaults_to_standard_tier() -> None:
    customer = Customer(
        customer_id="CUST-001",
        name="Jordan Example",
    )

    assert customer.tier is CustomerTier.STANDARD


def test_order_preserves_money_as_decimal() -> None:
    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        product_name="Wireless Headphones Pro",
        category="Electronics",
        unit_price=Decimal("149.99"),
        status=OrderStatus.DELIVERED,
        ordered_at=datetime.now(UTC),
    )

    assert order.unit_price == Decimal("149.99")


def test_policy_evidence_model() -> None:
    evidence = PolicyEvidence(
        policy_type=PolicyType.RETURNS,
        content="Premium customers have an extended return window.",
        source="returns-policy",
        relevance_score=0.91,
    )

    assert evidence.policy_type is PolicyType.RETURNS
    assert evidence.relevance_score == 0.91


def test_refund_decision_model() -> None:
    decision = RefundDecision(
        eligible=True,
        reason="Order falls within the permitted return window.",
        refund_amount=Decimal("149.99"),
        order_id="ORD-001",
    )

    assert decision.eligible is True
    assert decision.refund_amount == Decimal("149.99")


def test_policy_evidence_accepts_unbounded_non_negative_score() -> None:
    evidence = PolicyEvidence(
        policy_type=PolicyType.RETURNS,
        content="Policy evidence",
        source="returns-kb",
        relevance_score=1.25,
    )

    assert evidence.relevance_score == 1.25
