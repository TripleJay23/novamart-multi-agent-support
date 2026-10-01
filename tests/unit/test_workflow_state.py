import pytest

from novamart_support.domain import RequestType, WorkflowState
from novamart_support.exceptions import (
    ConcurrencyConflictError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)
from novamart_support.state.memory import InMemoryWorkflowStateRepository


def make_state(session_id: str = "session-001") -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        customer_id="CUST-001",
        original_query="Can I return my headphones?",
        request_type=RequestType.RETURN_REFUND,
    )


def test_create_and_get_workflow() -> None:
    repository = InMemoryWorkflowStateRepository()

    created = repository.create(make_state())
    loaded = repository.get(created.session_id)

    assert loaded.session_id == "session-001"
    assert loaded.version == 0
    assert loaded.customer_id == "CUST-001"


def test_duplicate_workflow_is_rejected() -> None:
    repository = InMemoryWorkflowStateRepository()
    state = make_state()

    repository.create(state)

    with pytest.raises(WorkflowAlreadyExistsError):
        repository.create(state)


def test_missing_workflow_is_rejected() -> None:
    repository = InMemoryWorkflowStateRepository()

    with pytest.raises(WorkflowNotFoundError):
        repository.get("missing")


def test_update_increments_version() -> None:
    repository = InMemoryWorkflowStateRepository()
    state = repository.create(make_state())

    updated = repository.update(
        state.session_id,
        {"route_history": ["InventoryAgent"]},
        expected_version=0,
    )

    assert updated.version == 1
    assert updated.route_history == ["InventoryAgent"]


def test_stale_update_is_rejected() -> None:
    repository = InMemoryWorkflowStateRepository()
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


def test_repository_does_not_leak_mutable_state() -> None:
    repository = InMemoryWorkflowStateRepository()
    state = repository.create(make_state())

    loaded = repository.get(state.session_id)
    loaded.route_history.append("UnexpectedMutation")

    stored = repository.get(state.session_id)

    assert stored.route_history == []
