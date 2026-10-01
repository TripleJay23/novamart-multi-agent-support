"""Deterministic refund and return eligibility rules."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from novamart_support.domain import (
    CustomerTier,
    OrderStatus,
    RefundDecision,
)
from novamart_support.services.inventory import InventoryService

RETURN_WINDOWS_DAYS: dict[CustomerTier, int] = {
    CustomerTier.STANDARD: 30,
    CustomerTier.PREMIUM: 60,
}


def utc_now() -> datetime:
    """Return current UTC time."""

    return datetime.now(UTC)


class RefundService:
    """Evaluate refund eligibility using trusted inventory data."""

    def __init__(
        self,
        inventory_service: InventoryService,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._inventory = inventory_service
        self._clock = clock

    def evaluate(
        self,
        customer_id: str,
        order_id: str,
    ) -> RefundDecision:
        customer = self._inventory.get_customer(customer_id)
        order = self._inventory.get_order(customer_id, order_id)

        if order.status is OrderStatus.REFUNDED:
            return RefundDecision(
                eligible=False,
                reason="Order has already been refunded.",
                order_id=order.order_id,
            )

        if order.status is not OrderStatus.DELIVERED:
            return RefundDecision(
                eligible=False,
                reason="Only delivered orders can be returned for a refund.",
                order_id=order.order_id,
            )

        if order.delivered_at is None:
            return RefundDecision(
                eligible=False,
                reason="Delivery date is unavailable, so refund eligibility cannot be verified.",
                order_id=order.order_id,
            )

        if not order.return_eligible:
            return RefundDecision(
                eligible=False,
                reason="This order is marked as ineligible for return.",
                order_id=order.order_id,
            )

        now = self._clock()
        elapsed = now - order.delivered_at

        if elapsed.total_seconds() < 0:
            return RefundDecision(
                eligible=False,
                reason="The recorded delivery date is in the future.",
                order_id=order.order_id,
            )

        return_window = RETURN_WINDOWS_DAYS[customer.tier]
        days_since_delivery = elapsed.days

        if days_since_delivery > return_window:
            return RefundDecision(
                eligible=False,
                reason=(
                    f"The {customer.tier.value} return window is "
                    f"{return_window} days and this order was delivered "
                    f"{days_since_delivery} days ago."
                ),
                order_id=order.order_id,
            )

        refund_amount = order.unit_price * Decimal(order.quantity)

        return RefundDecision(
            eligible=True,
            reason=(
                f"Order is within the {return_window}-day "
                f"{customer.tier.value} return window."
            ),
            refund_amount=refund_amount,
            order_id=order.order_id,
        )
