from datetime import UTC, datetime
from decimal import Decimal

import boto3
from moto import mock_aws

from novamart_support.config import Settings
from novamart_support.repositories import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)
from novamart_support.seed import build_demo_data, seed_demo_data
from novamart_support.services import InventoryService, RefundService

REFERENCE_TIME = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def make_settings() -> Settings:
    return Settings(
        AWS_REGION="us-east-1",
        PROJECT_NAME="novamart-support",
        _env_file=None,
    )


def create_tables(client: object) -> None:
    client.create_table(
        TableName="novamart-support-customers",
        AttributeDefinitions=[
            {
                "AttributeName": "customer_id",
                "AttributeType": "S",
            }
        ],
        KeySchema=[
            {
                "AttributeName": "customer_id",
                "KeyType": "HASH",
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    client.create_table(
        TableName="novamart-support-orders",
        AttributeDefinitions=[
            {
                "AttributeName": "customer_id",
                "AttributeType": "S",
            },
            {
                "AttributeName": "order_id",
                "AttributeType": "S",
            },
        ],
        KeySchema=[
            {
                "AttributeName": "customer_id",
                "KeyType": "HASH",
            },
            {
                "AttributeName": "order_id",
                "KeyType": "RANGE",
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def test_demo_data_contains_expected_business_scenarios() -> None:
    customers, orders = build_demo_data(REFERENCE_TIME)

    assert len(customers) == 2
    assert len(orders) == 4

    assert customers[0].customer_id == "CUST-1001"
    assert customers[0].tier.value == "premium"

    assert orders[0].order_id == "ORD-1001"
    assert orders[0].return_eligible is True

    assert orders[1].status.value == "shipped"
    assert orders[2].customer_id == "CUST-2001"
    assert orders[3].status.value == "refunded"


@mock_aws
def test_seed_demo_data_is_idempotent() -> None:
    client = boto3.client(
        "dynamodb",
        region_name="us-east-1",
    )
    create_tables(client)

    first = seed_demo_data(
        make_settings(),
        reference_time=REFERENCE_TIME,
        dynamodb_client=client,
    )
    second = seed_demo_data(
        make_settings(),
        reference_time=REFERENCE_TIME,
        dynamodb_client=client,
    )

    assert first.customers_created == 2
    assert first.orders_created == 4
    assert first.customers_skipped == 0
    assert first.orders_skipped == 0

    assert second.customers_created == 0
    assert second.orders_created == 0
    assert second.customers_skipped == 2
    assert second.orders_skipped == 4

    customer_scan = client.scan(
        TableName="novamart-support-customers"
    )
    order_scan = client.scan(
        TableName="novamart-support-orders"
    )

    assert customer_scan["Count"] == 2
    assert order_scan["Count"] == 4


@mock_aws
def test_seeded_data_drives_refund_scenarios() -> None:
    client = boto3.client(
        "dynamodb",
        region_name="us-east-1",
    )
    create_tables(client)

    settings = make_settings()

    seed_demo_data(
        settings,
        reference_time=REFERENCE_TIME,
        dynamodb_client=client,
    )

    customers = DynamoDBCustomerRepository(
        settings.resolved_customer_table_name,
        dynamodb_client=client,
    )
    orders = DynamoDBOrderRepository(
        settings.resolved_order_table_name,
        dynamodb_client=client,
    )

    inventory = InventoryService(
        customers,
        orders,
    )
    refunds = RefundService(
        inventory,
        clock=lambda: REFERENCE_TIME,
    )

    eligible = refunds.evaluate(
        "CUST-1001",
        "ORD-1001",
    )
    expired = refunds.evaluate(
        "CUST-2001",
        "ORD-2001",
    )

    assert eligible.eligible is True
    assert eligible.refund_amount == Decimal("149.99")

    assert expired.eligible is False
    assert "30 days" in expired.reason
