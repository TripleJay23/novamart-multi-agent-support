"""Reproduce local domain behavior without AWS calls or model inference.

Run from the repository root after installing development dependencies:
    uv run --locked --extra dev python docs/evidence/local_demo.py
"""

from datetime import UTC, datetime

from novamart_support.domain import RequestType
from novamart_support.repositories import InMemoryCustomerRepository, InMemoryOrderRepository
from novamart_support.seed import build_demo_data
from novamart_support.services import InventoryService, RefundService, WorkflowService
from novamart_support.state import InMemoryWorkflowStateRepository


def main() -> None:
    reference = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
    customers, orders = build_demo_data(reference)
    inventory = InventoryService(
        InMemoryCustomerRepository(customers),
        InMemoryOrderRepository(orders),
    )
    refunds = RefundService(inventory, clock=lambda: reference)
    workflows = WorkflowService(InMemoryWorkflowStateRepository())

    print("NovaMart | local domain demonstration")
    print(f"Reference clock: {reference.isoformat()}")
    print("Real services + in-memory repositories; no AWS or model calls.\n")

    for order in orders:
        decision = refunds.evaluate(order.customer_id, order.order_id)
        amount = (
            f"{decision.refund_amount:.2f}"
            if decision.refund_amount is not None
            else "n/a"
        )
        print(
            f"{order.customer_id} / {order.order_id} | "
            f"eligible={str(decision.eligible):<5} | "
            f"amount={amount}"
        )
        print(f"  {decision.reason}")

    print("\nRoutes from WorkflowService (after orchestrator classification):")
    for request_type in RequestType:
        route = " -> ".join(workflows.planned_route(request_type))
        print(f"  {request_type.value}: {route}")


if __name__ == "__main__":
    main()
