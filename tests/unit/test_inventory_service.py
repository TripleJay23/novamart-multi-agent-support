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
from novamart_support.services import InventoryService

NOW = datetime.now(UTC)


def make_service() -> InventoryService:
    customers = [
        Customer(
            customer_id="CUST-001",
            name="Alex Customer",
            tier=CustomerTier.PREMIUM,
        )
    ]

    orders = [
        Order(
            order_id="ORD-001",
            customer_id="CUST-001",
            product_name="Wireless Headphones Pro",
            category="Electronics",
            unit_price=Decimal("149.99"),
            status=OrderStatus.DELIVERED,
            ordered_at=NOW - timedelta(days=10),
            delivered_at=NOW - timedelta(days=7),
            return_eligible=True,
        ),
        Order(
            order_id="ORD-002",
            customer_id="CUST-001",
            product_name="Smart Speaker",
            category="Electronics",
            unit_price=Decimal("89.99"),
            status=OrderStatus.SHIPPED,
            ordered_at=NOW - timedelta(days=2),
        ),
    ]

    return InventoryService(
        InMemoryCustomerRepository(customers),
        InMemoryOrderRepository(orders),
    )


def test_get_customer_tier() -> None:
    service = make_service()

    assert service.get_customer_tier("CUST-001") is CustomerTier.PREMIUM


def test_get_order() -> None:
    service = make_service()

    order = service.get_order("CUST-001", "ORD-001")

    assert order.product_name == "Wireless Headphones Pro"


def test_orders_are_returned_newest_first() -> None:
    service = make_service()

    orders = service.list_customer_orders("CUST-001")

    assert [order.order_id for order in orders] == [
        "ORD-002",
        "ORD-001",
    ]


def test_missing_customer_fails() -> None:
    service = make_service()

    with pytest.raises(CustomerNotFoundError):
        service.get_customer("CUST-404")


def test_missing_order_fails() -> None:
    service = make_service()

    with pytest.raises(OrderNotFoundError):
        service.get_order("CUST-001", "ORD-404")
