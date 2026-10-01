"""In-memory customer and order repositories."""

from novamart_support.domain import Customer, Order
from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError


class InMemoryCustomerRepository:
    def __init__(self, customers: list[Customer] | None = None) -> None:
        self._customers = {
            customer.customer_id: customer.model_copy(deep=True)
            for customer in customers or []
        }

    def get(self, customer_id: str) -> Customer:
        try:
            return self._customers[customer_id].model_copy(deep=True)
        except KeyError as exc:
            raise CustomerNotFoundError(
                f"Customer not found: {customer_id}"
            ) from exc


class InMemoryOrderRepository:
    def __init__(self, orders: list[Order] | None = None) -> None:
        self._orders = {
            (order.customer_id, order.order_id): order.model_copy(deep=True)
            for order in orders or []
        }

    def get(self, customer_id: str, order_id: str) -> Order:
        try:
            return self._orders[(customer_id, order_id)].model_copy(deep=True)
        except KeyError as exc:
            raise OrderNotFoundError(
                f"Order not found: {customer_id}/{order_id}"
            ) from exc

    def list_by_customer(self, customer_id: str) -> list[Order]:
        return [
            order.model_copy(deep=True)
            for (owner_id, _), order in self._orders.items()
            if owner_id == customer_id
        ]
