import boto3
import pytest
from moto import mock_aws

from novamart_support.domain import (
    RequestType,
    WorkflowState,
)
from novamart_support.exceptions import (
    ConcurrencyConflictError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)
from novamart_support.state import DynamoDBWorkflowStateRepository

TABLE_NAME = "novamart-test-workflow-state"


@pytest.fixture
def repository() -> DynamoDBWorkflowStateRepository:
    with mock_aws():
        client = boto3.client(
            "dynamodb",
            region_name="us-east-1",
        )

        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {
                    "AttributeName": "session_id",
                    "KeyType": "HASH",
                }
            ],
            AttributeDefinitions=[
                {
                    "AttributeName": "session_id",
                    "AttributeType": "S",
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield DynamoDBWorkflowStateRepository(
            TABLE_NAME,
            dynamodb_client=client,
        )


def make_state() -> WorkflowState:
    return WorkflowState(
        session_id="session-001",
        customer_id="CUST-001",
        original_query="Can I return my headphones?",
        request_type=RequestType.RETURN_REFUND,
    )


def test_create_and_load(repository: DynamoDBWorkflowStateRepository) -> None:
    created = repository.create(make_state())
    loaded = repository.get(created.session_id)

    assert loaded == created


def test_duplicate_create_fails(
    repository: DynamoDBWorkflowStateRepository,
) -> None:
    state = make_state()

    repository.create(state)

    with pytest.raises(WorkflowAlreadyExistsError):
        repository.create(state)


def test_missing_workflow_fails(
    repository: DynamoDBWorkflowStateRepository,
) -> None:
    with pytest.raises(WorkflowNotFoundError):
        repository.get("missing")


def test_update_increments_version(
    repository: DynamoDBWorkflowStateRepository,
) -> None:
    state = repository.create(make_state())

    updated = repository.update(
        state.session_id,
        {
            "route_history": ["InventoryAgent"],
            "inventory_context": {
                "order_id": "ORD-001",
                "confidence": 0.95,
            },
        },
        expected_version=0,
    )

    assert updated.version == 1

    loaded = repository.get(state.session_id)

    assert loaded.version == 1
    assert loaded.route_history == ["InventoryAgent"]


def test_stale_version_fails(
    repository: DynamoDBWorkflowStateRepository,
) -> None:
    state = repository.create(make_state())

    repository.update(
        state.session_id,
        {"route_history": ["InventoryAgent"]},
        expected_version=0,
    )

    with pytest.raises(ConcurrencyConflictError):
        repository.update(
            state.session_id,
            {"route_history": ["PolicyAgent"]},
            expected_version=0,
        )
