"""DynamoDB adapters for NovaMart customer and order data."""

from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer

from novamart_support.domain import Customer, Order
from novamart_support.exceptions import CustomerNotFoundError, OrderNotFoundError


class _DynamoDBDecoder:
    def __init__(self) -> None:
        self._deserializer = TypeDeserializer()

    def decode(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            key: self._deserializer.deserialize(value)
            for key, value in item.items()
        }


class DynamoDBCustomerRepository:
    def __init__(
        self,
        table_name: str,
        *,
        region_name: str = "us-east-1",
        dynamodb_client: Any | None = None,
    ) -> None:
        self._table_name = table_name
        self._client = dynamodb_client or boto3.client(
            "dynamodb",
            region_name=region_name,
        )
        self._decoder = _DynamoDBDecoder()

    def get(self, customer_id: str) -> Customer:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={"customer_id": {"S": customer_id}},
            ConsistentRead=True,
        )

        item = response.get("Item")
        if item is None:
            raise CustomerNotFoundError(
                f"Customer not found: {customer_id}"
            )

        return Customer.model_validate(self._decoder.decode(item))


class DynamoDBOrderRepository:
    def __init__(
        self,
        table_name: str,
        *,
        region_name: str = "us-east-1",
        dynamodb_client: Any | None = None,
    ) -> None:
        self._table_name = table_name
        self._client = dynamodb_client or boto3.client(
            "dynamodb",
            region_name=region_name,
        )
        self._decoder = _DynamoDBDecoder()

    def get(self, customer_id: str, order_id: str) -> Order:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                "customer_id": {"S": customer_id},
                "order_id": {"S": order_id},
            },
            ConsistentRead=True,
        )

        item = response.get("Item")
        if item is None:
            raise OrderNotFoundError(
                f"Order not found: {customer_id}/{order_id}"
            )

        return Order.model_validate(self._decoder.decode(item))

    def list_by_customer(self, customer_id: str) -> list[Order]:
        response = self._client.query(
            TableName=self._table_name,
            KeyConditionExpression="customer_id = :customer_id",
            ExpressionAttributeValues={
                ":customer_id": {"S": customer_id},
            },
        )

        return [
            Order.model_validate(self._decoder.decode(item))
            for item in response.get("Items", [])
        ]
