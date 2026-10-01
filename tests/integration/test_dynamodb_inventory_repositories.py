from datetime import UTC, datetime
from decimal import Decimal

import boto3
import pytest
from boto3.dynamodb.types import TypeSerializer
from moto import mock_aws

from novamart_support.domain import CustomerTier, OrderStatus
from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError
from novamart_support.repositories import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)

CUSTOMERS_TABLE = "novamart-test-customers"
ORDERS_TABLE = "novamart-test-orders"


def encode(item: dict[str, object]) -> dict[str, object]:
    serializer = TypeSerializer()
    return {
        key: serializer.serialize(value)
        for key, value in item.items()
    }


@pytest.fixture
def repositories() -> tuple[
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
]:
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")

        client.create_table(
            TableName=CUSTOMERS_TABLE,
            KeySchema=[
                {"AttributeName": "customer_id", "KeyType": "HASH"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "customer_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        client.create_table(
            TableName=ORDERS_TABLE,
            KeySchema=[
                {"AttributeName": "customer_id", "KeyType": "HASH"},
                {"AttributeName": "order_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "customer_id", "AttributeType": "S"},
                {"AttributeName": "order_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        client.put_item(
            TableName=CUSTOMERS_TABLE,
            Item=encode(
                {
                    "customer_id": "CUST-001",
                    "name": "Alex Customer",
                    "tier": "premium",
                    "email": "alex@example.test",
                }
            ),
        )

        client.put_item(
            TableName=ORDERS_TABLE,
            Item=encode(
                {
                    "customer_id": "CUST-001",
                    "order_id": "ORD-001",
                    "product_name": "Wireless Headphones Pro",
                    "category": "Electronics",
                    "unit_price": Decimal("149.99"),
                    "quantity": 1,
                    "status": "delivered",
                    "ordered_at": datetime(2026, 9, 10, tzinfo=UTC).isoformat(),
                    "delivered_at": datetime(2026, 9, 13, tzinfo=UTC).isoformat(),
                    "return_eligible": True,
                }
            ),
        )

        yield (
            DynamoDBCustomerRepository(
                CUSTOMERS_TABLE,
                dynamodb_client=client,
            ),
            DynamoDBOrderRepository(
                ORDERS_TABLE,
                dynamodb_client=client,
            ),
        )


def test_customer_round_trip(repositories) -> None:
    customers, _ = repositories

    customer = customers.get("CUST-001")

    assert customer.tier is CustomerTier.PREMIUM


def test_order_round_trip_preserves_decimal(repositories) -> None:
    _, orders = repositories

    order = orders.get("CUST-001", "ORD-001")

    assert order.status is OrderStatus.DELIVERED
    assert order.unit_price == Decimal("149.99")


def test_list_customer_orders(repositories) -> None:
    _, orders = repositories

    result = orders.list_by_customer("CUST-001")

    assert len(result) == 1
    assert result[0].order_id == "ORD-001"


def test_missing_customer(repositories) -> None:
    customers, _ = repositories

    with pytest.raises(CustomerNotFoundError):
        customers.get("CUST-404")


def test_missing_order(repositories) -> None:
    _, orders = repositories

    with pytest.raises(OrderNotFoundError):
        orders.get("CUST-001", "ORD-404")
