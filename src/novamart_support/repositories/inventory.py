"""Repository contracts and adapters for customers and orders."""

from typing import Protocol

from novamart_support.domain import Customer, Order


class CustomerRepository(Protocol):
    """Customer persistence contract."""

    def get(self, customer_id: str) -> Customer:
        """Return a customer by ID."""


class OrderRepository(Protocol):
    """Order persistence contract."""

    def get(self, customer_id: str, order_id: str) -> Order:
        """Return an order belonging to a customer."""

    def list_by_customer(self, customer_id: str) -> list[Order]:
        """Return all orders belonging to a customer."""
