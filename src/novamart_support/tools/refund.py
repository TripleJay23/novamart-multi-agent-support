"""Agent-facing refund eligibility tool handlers."""

from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError
from novamart_support.services import RefundService
from novamart_support.tools.result import ToolResponse, failure, success


class RefundToolHandlers:
    """Expose deterministic refund eligibility to an agent layer."""

    def __init__(self, service: RefundService) -> None:
        self._service = service

    def evaluate_refund(
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
            decision = self._service.evaluate(
                cleaned_customer_id,
                cleaned_order_id,
            )
        except CustomerNotFoundError as exc:
            return failure("customer_not_found", str(exc))
        except OrderNotFoundError as exc:
            return failure("order_not_found", str(exc))

        return success(decision.model_dump(mode="json"))
