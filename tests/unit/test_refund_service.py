from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from novamart_support.domain import (
    Customer,
    CustomerTier,
    Order,
    OrderStatus,
)
from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError
from novamart_support.repositories import (
    InMemoryCustomerRepository,
    InMemoryOrderRepository,
)
from novamart_support.services import InventoryService, RefundService

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_service(
    *,
    tier: CustomerTier = CustomerTier.STANDARD,
    status: OrderStatus = OrderStatus.DELIVERED,
    delivered_days_ago: int | None = 10,
    return_eligible: bool = True,
    quantity: int = 1,
) -> RefundService:
    customer = Customer(
        customer_id="CUST-001",
        name="Alex Customer",
        tier=tier,
    )

    delivered_at = (
        NOW - timedelta(days=delivered_days_ago)
        if delivered_days_ago is not None
        else None
    )

    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        product_name="Wireless Headphones Pro",
        category="Electronics",
        unit_price=Decimal("149.99"),
        quantity=quantity,
        status=status,
        ordered_at=NOW - timedelta(days=70),
        delivered_at=delivered_at,
        return_eligible=return_eligible,
    )

    inventory = InventoryService(
        InMemoryCustomerRepository([customer]),
        InMemoryOrderRepository([order]),
    )

    return RefundService(
        inventory,
        clock=lambda: NOW,
    )


def test_standard_customer_within_30_days_is_eligible() -> None:
    service = make_service(
        tier=CustomerTier.STANDARD,
        delivered_days_ago=30,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is True
    assert decision.refund_amount == Decimal("149.99")


def test_standard_customer_after_30_days_is_ineligible() -> None:
    service = make_service(
        tier=CustomerTier.STANDARD,
        delivered_days_ago=31,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "30 days" in decision.reason


def test_premium_customer_within_60_days_is_eligible() -> None:
    service = make_service(
        tier=CustomerTier.PREMIUM,
        delivered_days_ago=60,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is True


def test_premium_customer_after_60_days_is_ineligible() -> None:
    service = make_service(
        tier=CustomerTier.PREMIUM,
        delivered_days_ago=61,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "60 days" in decision.reason


def test_non_delivered_order_is_ineligible() -> None:
    service = make_service(
        status=OrderStatus.SHIPPED,
        delivered_days_ago=None,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "delivered orders" in decision.reason


def test_already_refunded_order_is_ineligible() -> None:
    service = make_service(
        status=OrderStatus.REFUNDED,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "already been refunded" in decision.reason


def test_missing_delivery_date_is_ineligible() -> None:
    service = make_service(
        delivered_days_ago=None,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "Delivery date is unavailable" in decision.reason


def test_order_marked_not_returnable_is_ineligible() -> None:
    service = make_service(
        return_eligible=False,
    )

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "ineligible for return" in decision.reason


def test_refund_amount_accounts_for_quantity() -> None:
    service = make_service(quantity=3)

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is True
    assert decision.refund_amount == Decimal("449.97")


def test_future_delivery_date_is_rejected() -> None:
    service = make_service(delivered_days_ago=-1)

    decision = service.evaluate("CUST-001", "ORD-001")

    assert decision.eligible is False
    assert "future" in decision.reason


def test_missing_customer_propagates_domain_error() -> None:
    service = make_service()

    with pytest.raises(CustomerNotFoundError):
        service.evaluate("CUST-404", "ORD-001")


def test_missing_order_propagates_domain_error() -> None:
    service = make_service()

    with pytest.raises(OrderNotFoundError):
        service.evaluate("CUST-001", "ORD-404")
