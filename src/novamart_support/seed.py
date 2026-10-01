"""Seed reproducible NovaMart demo customer and order data."""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

import boto3
from boto3.dynamodb.types import TypeSerializer
from botocore.exceptions import ClientError
from pydantic import BaseModel

from novamart_support.config import Settings, get_settings
from novamart_support.domain import (
    Customer,
    CustomerTier,
    Order,
    OrderStatus,
)


@dataclass(frozen=True)
class SeedSummary:
    """Result of one demo-data seeding run."""

    reference_time: str
    customers_created: int
    customers_skipped: int
    orders_created: int
    orders_skipped: int


def build_demo_data(
    reference_time: datetime,
) -> tuple[list[Customer], list[Order]]:
    """Build deterministic scenarios relative to a supplied UTC reference."""

    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise ValueError("reference_time must be timezone-aware")

    reference_time = reference_time.astimezone(UTC)

    customers = [
        Customer(
            customer_id="CUST-1001",
            name="Amina Hassan",
            tier=CustomerTier.PREMIUM,
            email="amina.hassan@example.com",
        ),
        Customer(
            customer_id="CUST-2001",
            name="Daniel Mushi",
            tier=CustomerTier.STANDARD,
            email="daniel.mushi@example.com",
        ),
    ]

    orders = [
        Order(
            order_id="ORD-1001",
            customer_id="CUST-1001",
            product_name="Wireless Headphones Pro",
            category="Electronics",
            unit_price=Decimal("149.99"),
            quantity=1,
            status=OrderStatus.DELIVERED,
            ordered_at=reference_time - timedelta(days=18),
            delivered_at=reference_time - timedelta(days=10),
            return_eligible=True,
        ),
        Order(
            order_id="ORD-1002",
            customer_id="CUST-1001",
            product_name="Smart Watch Series 5",
            category="Electronics",
            unit_price=Decimal("249.50"),
            quantity=1,
            status=OrderStatus.SHIPPED,
            ordered_at=reference_time - timedelta(days=3),
            delivered_at=None,
            return_eligible=False,
        ),
        Order(
            order_id="ORD-2001",
            customer_id="CUST-2001",
            product_name="Ergonomic Office Chair",
            category="Home & Office",
            unit_price=Decimal("320.00"),
            quantity=1,
            status=OrderStatus.DELIVERED,
            ordered_at=reference_time - timedelta(days=50),
            delivered_at=reference_time - timedelta(days=35),
            return_eligible=True,
        ),
        Order(
            order_id="ORD-2002",
            customer_id="CUST-2001",
            product_name="USB-C Hub",
            category="Electronics",
            unit_price=Decimal("59.99"),
            quantity=2,
            status=OrderStatus.REFUNDED,
            ordered_at=reference_time - timedelta(days=20),
            delivered_at=reference_time - timedelta(days=12),
            return_eligible=True,
        ),
    ]

    return customers, orders


def _normalise(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {
            key: _normalise(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_normalise(item) for item in value]

    return value


def _serialize_model(
    model: BaseModel,
    serializer: TypeSerializer,
) -> dict[str, Any]:
    raw = _normalise(model.model_dump(mode="python"))

    return {
        key: serializer.serialize(value)
        for key, value in raw.items()
    }


def _put_if_absent(
    client: Any,
    *,
    table_name: str,
    item: dict[str, Any],
    key_attribute: str,
) -> bool:
    try:
        client.put_item(
            TableName=table_name,
            Item=item,
            ConditionExpression="attribute_not_exists(#key)",
            ExpressionAttributeNames={
                "#key": key_attribute,
            },
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise

    return True


def seed_demo_data(
    settings: Settings,
    *,
    reference_time: datetime | None = None,
    dynamodb_client: Any | None = None,
) -> SeedSummary:
    """Seed demo customers/orders without overwriting existing records."""

    reference = reference_time or datetime.now(UTC)
    reference = reference.astimezone(UTC)

    customers, orders = build_demo_data(reference)

    client = dynamodb_client or boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
    )
    serializer = TypeSerializer()

    customers_created = 0
    customers_skipped = 0
    orders_created = 0
    orders_skipped = 0

    for customer in customers:
        created = _put_if_absent(
            client,
            table_name=settings.resolved_customer_table_name,
            item=_serialize_model(customer, serializer),
            key_attribute="customer_id",
        )

        if created:
            customers_created += 1
        else:
            customers_skipped += 1

    for order in orders:
        created = _put_if_absent(
            client,
            table_name=settings.resolved_order_table_name,
            item=_serialize_model(order, serializer),
            key_attribute="order_id",
        )

        if created:
            orders_created += 1
        else:
            orders_skipped += 1

    return SeedSummary(
        reference_time=reference.isoformat(),
        customers_created=customers_created,
        customers_skipped=customers_skipped,
        orders_created=orders_created,
        orders_skipped=orders_skipped,
    )


def _parse_reference_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "reference time must be ISO-8601"
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError(
            "reference time must include a timezone"
        )

    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novamart-seed",
        description="Seed NovaMart demo customer and order data.",
    )

    parser.add_argument(
        "--reference-time",
        type=_parse_reference_time,
        help=(
            "ISO-8601 scenario reference time. "
            "Defaults to the current UTC time."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the seed summary as JSON.",
    )

    return parser


def main() -> int:
    args = build_parser().parse_args()

    summary = seed_demo_data(
        get_settings(),
        reference_time=args.reference_time,
    )

    if args.json:
        print(
            json.dumps(
                asdict(summary),
                indent=2,
            )
        )
    else:
        print(
            "NovaMart demo seed complete: "
            f"{summary.customers_created} customers created, "
            f"{summary.customers_skipped} skipped; "
            f"{summary.orders_created} orders created, "
            f"{summary.orders_skipped} skipped."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
