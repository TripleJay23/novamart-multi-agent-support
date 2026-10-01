"""In-memory workflow repository used for local execution and unit tests."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from novamart_support.domain import WorkflowState
from novamart_support.domain.models import utc_now
from novamart_support.exceptions import (
    ConcurrencyConflictError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)


class InMemoryWorkflowStateRepository:
    """In-memory implementation of the workflow-state repository contract."""

    def __init__(self) -> None:
        self._states: dict[str, WorkflowState] = {}

    def create(self, state: WorkflowState) -> WorkflowState:
        if state.session_id in self._states:
            raise WorkflowAlreadyExistsError(
                f"Workflow already exists: {state.session_id}"
            )

        stored = state.model_copy(deep=True)
        self._states[state.session_id] = stored
        return deepcopy(stored)

    def get(self, session_id: str) -> WorkflowState:
        try:
            return deepcopy(self._states[session_id])
        except KeyError as exc:
            raise WorkflowNotFoundError(
                f"Workflow not found: {session_id}"
            ) from exc

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

        stored = current.model_copy(
            update={
                **dict(updates),
                "version": current.version + 1,
                "updated_at": utc_now(),
            },
            deep=True,
        )

        self._states[session_id] = stored
        return deepcopy(stored)
