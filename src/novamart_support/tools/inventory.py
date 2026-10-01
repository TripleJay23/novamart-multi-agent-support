"""Agent-facing inventory tool handlers."""

from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError
from novamart_support.services import InventoryService
from novamart_support.tools.result import ToolResponse, failure, success


class InventoryToolHandlers:
    """Expose bounded inventory operations to an agent layer."""

    def __init__(self, service: InventoryService) -> None:
        self._service = service

    def get_customer_profile(self, customer_id: str) -> ToolResponse:
        cleaned_customer_id = customer_id.strip()

        if not cleaned_customer_id:
            return failure(
                "invalid_input",
                "customer_id must not be empty.",
            )

        try:
            customer = self._service.get_customer(cleaned_customer_id)
        except CustomerNotFoundError as exc:
            return failure("customer_not_found", str(exc))

        # Email is intentionally omitted from the general-purpose profile tool.
        return success(
            {
                "customer_id": customer.customer_id,
                "name": customer.name,
                "tier": customer.tier.value,
            }
        )

    def get_order(
        self,
        customer_id: str,
        order_id: str,
    ) -> ToolResponse:
        cleaned_customer_id = customer_id.strip()
        cleaned_order_id = order_id.strip()

        if not cleaned_customer_id or not cleaned_order_id:
            return failure(
                "invalid_input",
                "customer_id and order_id must not be empty.",
            )

        try:
            order = self._service.get_order(
                cleaned_customer_id,
                cleaned_order_id,
            )
        except OrderNotFoundError as exc:
            return failure("order_not_found", str(exc))

        return success(order.model_dump(mode="json"))

    def list_customer_orders(
        self,
        customer_id: str,
    ) -> ToolResponse:
        cleaned_customer_id = customer_id.strip()

        if not cleaned_customer_id:
            return failure(
                "invalid_input",
                "customer_id must not be empty.",
            )

        try:
            orders = self._service.list_customer_orders(
                cleaned_customer_id
            )
        except CustomerNotFoundError as exc:
            return failure("customer_not_found", str(exc))

        return success(
            {
                "customer_id": cleaned_customer_id,
                "orders": [
                    order.model_dump(mode="json")
                    for order in orders
                ],
            }
        )
