from datetime import UTC, datetime, timedelta
from decimal import Decimal

from novamart_support.domain import (
    Customer,
    CustomerTier,
    Order,
    OrderStatus,
    PolicyEvidence,
    PolicyType,
)
from novamart_support.rag import PolicyRetriever
from novamart_support.repositories import (
    InMemoryCustomerRepository,
    InMemoryOrderRepository,
)
from novamart_support.services import (
    InventoryService,
    PolicyService,
    RefundService,
)
from novamart_support.tools import (
    InventoryToolHandlers,
    PolicyToolHandlers,
    RefundToolHandlers,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


class FakePolicyRetriever:
    def __init__(
        self,
        policy_type: PolicyType,
        evidence: list[PolicyEvidence],
    ) -> None:
        self._policy_type = policy_type
        self._evidence = evidence

    @property
    def policy_type(self) -> PolicyType:
        return self._policy_type

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        return self._evidence[:limit]


def build_inventory_service() -> InventoryService:
    customer = Customer(
        customer_id="CUST-001",
        name="Alex Customer",
        tier=CustomerTier.PREMIUM,
        email="alex@example.test",
    )

    orders = [
        Order(
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
        InMemoryCustomerRepository([customer]),
        InMemoryOrderRepository(orders),
    )


def test_customer_profile_omits_email() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.get_customer_profile("CUST-001")

    assert response["ok"] is True
    assert response["data"] == {
        "customer_id": "CUST-001",
        "name": "Alex Customer",
        "tier": "premium",
    }
    assert "email" not in response["data"]


def test_missing_customer_returns_controlled_error() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.get_customer_profile("CUST-404")

    assert response["ok"] is False
    assert response["error"]["code"] == "customer_not_found"


def test_order_is_json_safe() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.get_order("CUST-001", "ORD-001")

    assert response["ok"] is True
    assert response["data"]["unit_price"] == "149.99"
    assert isinstance(response["data"]["ordered_at"], str)


def test_missing_order_returns_controlled_error() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.get_order("CUST-001", "ORD-404")

    assert response["ok"] is False
    assert response["error"]["code"] == "order_not_found"


def test_orders_remain_newest_first() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.list_customer_orders("CUST-001")

    assert response["ok"] is True
    assert [
        order["order_id"]
        for order in response["data"]["orders"]
    ] == [
        "ORD-002",
        "ORD-001",
    ]


def test_inventory_handler_rejects_empty_identifier() -> None:
    handlers = InventoryToolHandlers(build_inventory_service())

    response = handlers.get_customer_profile("   ")

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_input"


def test_refund_handler_returns_deterministic_decision() -> None:
    inventory = build_inventory_service()

    handlers = RefundToolHandlers(
        RefundService(
            inventory,
            clock=lambda: NOW,
        )
    )

    response = handlers.evaluate_refund(
        "CUST-001",
        "ORD-001",
    )

    assert response["ok"] is True
    assert response["data"]["eligible"] is True
    assert response["data"]["refund_amount"] == "299.98"


def test_refund_handler_returns_missing_order_error() -> None:
    inventory = build_inventory_service()

    handlers = RefundToolHandlers(
        RefundService(
            inventory,
            clock=lambda: NOW,
        )
    )

    response = handlers.evaluate_refund(
        "CUST-001",
        "ORD-404",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "order_not_found"


def test_policy_handler_returns_grounded_evidence() -> None:
    retriever: PolicyRetriever = FakePolicyRetriever(
        PolicyType.RETURNS,
        [
            PolicyEvidence(
                policy_type=PolicyType.RETURNS,
                content="Premium customers have an extended return window.",
                source="returns-kb",
                relevance_score=0.95,
            )
        ],
    )

    handlers = PolicyToolHandlers(
        PolicyService([retriever])
    )

    response = handlers.search_policies(
        "premium return window",
    )

    assert response["ok"] is True
    assert response["data"]["is_partial"] is False
    assert len(response["data"]["evidence"]) == 1
    assert (
        response["data"]["evidence"][0]["policy_type"]
        == "returns"
    )


def test_policy_handler_converts_no_evidence_to_controlled_error() -> None:
    retriever: PolicyRetriever = FakePolicyRetriever(
        PolicyType.RETURNS,
        [],
    )

    handlers = PolicyToolHandlers(
        PolicyService([retriever])
    )

    response = handlers.search_policies(
        "unknown policy",
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "policy_retrieval_failed"


def test_policy_handler_rejects_empty_query() -> None:
    retriever: PolicyRetriever = FakePolicyRetriever(
        PolicyType.RETURNS,
        [],
    )

    handlers = PolicyToolHandlers(
        PolicyService([retriever])
    )

    response = handlers.search_policies("   ")

    assert response["ok"] is False
    assert response["error"]["code"] == "invalid_input"
