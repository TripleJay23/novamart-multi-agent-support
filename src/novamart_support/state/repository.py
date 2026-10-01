"""Workflow-state repository contracts."""

from collections.abc import Mapping
from typing import Any, Protocol

from novamart_support.domain import WorkflowState


class WorkflowStateRepository(Protocol):
    """Persistence contract for shared workflow state."""

    def create(self, state: WorkflowState) -> WorkflowState:
        """Persist a new workflow."""

    def get(self, session_id: str) -> WorkflowState:
        """Retrieve an existing workflow."""

    def update(
        self,
        session_id: str,
        updates: Mapping[str, Any],
        *,
        expected_version: int,
    ) -> WorkflowState:
        """Update a workflow using optimistic concurrency control."""
