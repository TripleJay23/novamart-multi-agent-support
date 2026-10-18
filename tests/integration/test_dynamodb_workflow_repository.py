import json
from decimal import Decimal
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_aws

from novamart_support.domain import (
    RequestType,
    WorkflowState,
    WorkflowStatus,
)
from novamart_support.exceptions import (
    ConcurrencyConflictError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)
from novamart_support.runtime.execution import MultiAgentRuntime
from novamart_support.runtime.outputs import CommunicationAgentOutput, RefundAgentOutput
from novamart_support.services.workflow import WorkflowService
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


def test_resume_serializes_numeric_context_loaded_from_dynamodb(
    repository: DynamoDBWorkflowStateRepository,
) -> None:
    service = WorkflowService(repository)
    service.create_workflow(
        "numeric-resume", "Can I return ORD-001?", RequestType.RETURN_REFUND,
        customer_id="CUST-001",
    )
    service.record_inventory_context(
        "numeric-resume",
        {"orders": [{"order_id": "ORD-001", "unit_price": 149.99, "quantity": 2}]},
    )
    loaded = repository.get("numeric-resume")
    assert loaded.inventory_context is not None
    assert loaded.inventory_context["orders"][0]["unit_price"] == Decimal("149.99")
    calls = []

    def agent(prompt: str, *, structured_output_model: type) -> SimpleNamespace:
        calls.append(structured_output_model)
        if structured_output_model is RefundAgentOutput:
            payload = json.loads(prompt.split("WORKFLOW:\n", 1)[1])
            assert payload["inventory_context"]["orders"][0] == {
                "order_id": "ORD-001", "unit_price": "149.99", "quantity": "2",
            }
            output = RefundAgentOutput(context={"eligible": True, "refund_amount": "299.98"})
        else:
            assert structured_output_model is CommunicationAgentOutput
            output = CommunicationAgentOutput(final_response="Eligible amount: 299.98.")
        return SimpleNamespace(structured_output=output)

    runtime = MultiAgentRuntime(
        service, orchestrator_agent=agent, inventory_agent=agent, policy_agent=agent,
        refund_agent=agent, communication_agent=agent,
    )
    result = runtime.resume("numeric-resume")
    assert result.status is WorkflowStatus.COMPLETED
    assert result.route_history == ["InventoryAgent", "RefundAgent", "CommunicationAgent"]
    assert repository.get("numeric-resume").final_response == "Eligible amount: 299.98."
    assert runtime.resume("numeric-resume") == result
    assert calls == [RefundAgentOutput, CommunicationAgentOutput]
