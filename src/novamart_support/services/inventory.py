"""Inventory application service.

Agents depend on this service instead of talking directly to DynamoDB.
"""

from novamart_support.domain import Customer, CustomerTier, Order
from novamart_support.repositories.inventory import CustomerRepository, OrderRepository


class InventoryService:
    def __init__(
        self,
        customer_repository: CustomerRepository,
        order_repository: OrderRepository,
    ) -> None:
        self._customers = customer_repository
        self._orders = order_repository

    def get_customer(self, customer_id: str) -> Customer:
        return self._customers.get(customer_id)

    def get_customer_tier(self, customer_id: str) -> CustomerTier:
        return self.get_customer(customer_id).tier

    def get_order(self, customer_id: str, order_id: str) -> Order:
        return self._orders.get(customer_id, order_id)

    def list_customer_orders(self, customer_id: str) -> list[Order]:
        self.get_customer(customer_id)

        return sorted(
            self._orders.list_by_customer(customer_id),
            key=lambda order: order.ordered_at,
            reverse=True,
        )
