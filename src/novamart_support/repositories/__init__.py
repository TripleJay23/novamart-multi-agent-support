"""Persistence adapters for NovaMart business data."""

from novamart_support.repositories.dynamodb import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)
from novamart_support.repositories.inventory import CustomerRepository, OrderRepository
from novamart_support.repositories.memory import (
    InMemoryCustomerRepository,
    InMemoryOrderRepository,
)

__all__ = [
    "CustomerRepository",
    "DynamoDBCustomerRepository",
    "DynamoDBOrderRepository",
    "InMemoryCustomerRepository",
    "InMemoryOrderRepository",
    "OrderRepository",
]
