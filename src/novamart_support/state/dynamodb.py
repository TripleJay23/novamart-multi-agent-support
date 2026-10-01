"""DynamoDB-backed workflow-state repository."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from novamart_support.domain import WorkflowState
from novamart_support.domain.models import utc_now
from novamart_support.exceptions import (
    ConcurrencyConflictError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)


def _normalise_numbers(value: Any) -> Any:
    """Convert floats recursively to Decimal for DynamoDB compatibility."""

    if isinstance(value, float):
        return Decimal(str(value))

    if isinstance(value, dict):
        return {key: _normalise_numbers(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_normalise_numbers(item) for item in value]

    return value


class DynamoDBWorkflowStateRepository:
    """Persist workflow state in DynamoDB using optimistic locking."""

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
        self._serializer = TypeSerializer()
        self._deserializer = TypeDeserializer()

    def _serialize_state(self, state: WorkflowState) -> dict[str, Any]:
        raw = state.model_dump(mode="json")
        normalised = _normalise_numbers(raw)

        return {
            key: self._serializer.serialize(value)
            for key, value in normalised.items()
        }

    def _deserialize_state(
        self,
        item: Mapping[str, Any],
    ) -> WorkflowState:
        raw = {
            key: self._deserializer.deserialize(value)
            for key, value in item.items()
        }
        return WorkflowState.model_validate(raw)

    def create(self, state: WorkflowState) -> WorkflowState:
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item=self._serialize_state(state),
                ConditionExpression="attribute_not_exists(session_id)",
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise WorkflowAlreadyExistsError(
                    f"Workflow already exists: {state.session_id}"
                ) from exc
            raise

        return state.model_copy(deep=True)

    def get(self, session_id: str) -> WorkflowState:
        response = self._client.get_item(
            TableName=self._table_name,
            Key={
                "session_id": self._serializer.serialize(session_id),
            },
            ConsistentRead=True,
        )

        item = response.get("Item")
        if item is None:
            raise WorkflowNotFoundError(
                f"Workflow not found: {session_id}"
            )

        return self._deserialize_state(item)

    def update(
        self,
        session_id: str,
        updates: Mapping[str, Any],
        *,
        expected_version: int,
    ) -> WorkflowState:
        current = self.get(session_id)

        if current.version != expected_version:
            raise ConcurrencyConflictError(
                f"Workflow {session_id} version conflict: "
                f"expected {expected_version}, current {current.version}"
            )

        updated = current.model_copy(
            update={
                **dict(updates),
                "version": current.version + 1,
                "updated_at": utc_now(),
            },
            deep=True,
        )

        try:
            self._client.put_item(
                TableName=self._table_name,
                Item=self._serialize_state(updated),
                ConditionExpression="#version = :expected_version",
                ExpressionAttributeNames={
                    "#version": "version",
                },
                ExpressionAttributeValues={
                    ":expected_version": self._serializer.serialize(
                        expected_version
                    ),
                },
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                raise ConcurrencyConflictError(
                    f"Workflow {session_id} was modified concurrently"
                ) from exc
            raise

        return updated
