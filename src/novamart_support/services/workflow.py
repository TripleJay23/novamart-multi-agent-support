"""Deterministic workflow orchestration for NovaMart support requests."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Final

from novamart_support.domain import (
    RequestType,
    WorkflowState,
    WorkflowStatus,
)
from novamart_support.exceptions import WorkflowTransitionError
from novamart_support.state.repository import WorkflowStateRepository

INVENTORY_AGENT: Final = "InventoryAgent"
POLICY_AGENT: Final = "PolicyAgent"
REFUND_AGENT: Final = "RefundAgent"
COMMUNICATION_AGENT: Final = "CommunicationAgent"


ROUTES: Final[dict[RequestType, tuple[str, ...]]] = {
    RequestType.ORDER: (
        INVENTORY_AGENT,
        COMMUNICATION_AGENT,
    ),
    RequestType.RETURN_REFUND: (
        INVENTORY_AGENT,
        REFUND_AGENT,
        COMMUNICATION_AGENT,
    ),
    RequestType.POLICY: (
        POLICY_AGENT,
        COMMUNICATION_AGENT,
    ),
    RequestType.ACCOUNT: (
        INVENTORY_AGENT,
        COMMUNICATION_AGENT,
    ),
    RequestType.CALCULATION: (
        COMMUNICATION_AGENT,
    ),
    RequestType.GENERAL: (
        COMMUNICATION_AGENT,
    ),
}


class WorkflowService:
    """Manage deterministic routing and persisted workflow transitions."""

    def __init__(
        self,
        repository: WorkflowStateRepository,
    ) -> None:
        self._repository = repository

    def create_workflow(
        self,
        session_id: str,
        original_query: str,
        request_type: RequestType,
        *,
        customer_id: str | None = None,
    ) -> WorkflowState:
        """Create a classified support workflow."""

        cleaned_session_id = session_id.strip()
        cleaned_query = original_query.strip()

        if not cleaned_session_id:
            raise ValueError("session_id must not be empty.")

        if not cleaned_query:
            raise ValueError("original_query must not be empty.")

        cleaned_customer_id = (
            customer_id.strip()
            if customer_id is not None
            else None
        )

        if cleaned_customer_id == "":
            cleaned_customer_id = None

        return self._repository.create(
            WorkflowState(
                session_id=cleaned_session_id,
                customer_id=cleaned_customer_id,
                original_query=cleaned_query,
                request_type=request_type,
            )
        )

    def get_workflow(
        self,
        session_id: str,
    ) -> WorkflowState:
        """Restore an existing support workflow."""

        cleaned_session_id = session_id.strip()

        if not cleaned_session_id:
            raise ValueError("session_id must not be empty.")

        return self._repository.get(cleaned_session_id)

    def planned_route(
        self,
        request_type: RequestType,
    ) -> tuple[str, ...]:
        """Return the deterministic specialist route for a request type."""

        return ROUTES[request_type]

    def next_agent(
        self,
        session_id: str,
    ) -> str | None:
        """Return the next valid agent for an active workflow."""

        state = self.get_workflow(session_id)

        if state.status is not WorkflowStatus.ACTIVE:
            return None

        return self._next_agent_for_state(state)

    def record_inventory_context(
        self,
        session_id: str,
        context: Mapping[str, Any],
    ) -> WorkflowState:
        """Persist InventoryAgent output and advance the route."""

        return self._record_specialist_context(
            session_id,
            INVENTORY_AGENT,
            "inventory_context",
            context,
        )

    def record_policy_context(
        self,
        session_id: str,
        context: Mapping[str, Any],
    ) -> WorkflowState:
        """Persist PolicyAgent output and advance the route."""

        return self._record_specialist_context(
            session_id,
            POLICY_AGENT,
            "policy_context",
            context,
        )

    def record_refund_context(
        self,
        session_id: str,
        context: Mapping[str, Any],
    ) -> WorkflowState:
        """Persist RefundAgent output and advance the route."""

        return self._record_specialist_context(
            session_id,
            REFUND_AGENT,
            "refund_context",
            context,
        )

    def complete(
        self,
        session_id: str,
        final_response: str,
    ) -> WorkflowState:
        """Record CommunicationAgent output and complete the workflow."""

        cleaned_response = final_response.strip()

        if not cleaned_response:
            raise ValueError("final_response must not be empty.")

        state = self.get_workflow(session_id)
        self._require_active(state)

        expected_agent = self._next_agent_for_state(state)

        if expected_agent != COMMUNICATION_AGENT:
            raise WorkflowTransitionError(
                f"Workflow {state.session_id} cannot complete yet; "
                f"next agent is {expected_agent}."
            )

        return self._repository.update(
            state.session_id,
            {
                "route_history": [
                    *state.route_history,
                    COMMUNICATION_AGENT,
                ],
                "final_response": cleaned_response,
                "status": WorkflowStatus.COMPLETED,
            },
            expected_version=state.version,
        )

    def mark_failed(
        self,
        session_id: str,
    ) -> WorkflowState:
        """Move an active workflow into the failed terminal state."""

        state = self.get_workflow(session_id)
        self._require_active(state)

        return self._repository.update(
            state.session_id,
            {
                "status": WorkflowStatus.FAILED,
            },
            expected_version=state.version,
        )

    def _record_specialist_context(
        self,
        session_id: str,
        agent_name: str,
        field_name: str,
        context: Mapping[str, Any],
    ) -> WorkflowState:
        if not context:
            raise ValueError("specialist context must not be empty.")

        state = self.get_workflow(session_id)
        self._require_active(state)

        expected_agent = self._next_agent_for_state(state)

        if expected_agent != agent_name:
            raise WorkflowTransitionError(
                f"Workflow {state.session_id} expected "
                f"{expected_agent}, not {agent_name}."
            )

        return self._repository.update(
            state.session_id,
            {
                field_name: deepcopy(dict(context)),
                "route_history": [
                    *state.route_history,
                    agent_name,
                ],
            },
            expected_version=state.version,
        )

    def _next_agent_for_state(
        self,
        state: WorkflowState,
    ) -> str | None:
        route = self.planned_route(state.request_type)
        history = tuple(state.route_history)

        if len(history) > len(route) or history != route[: len(history)]:
            raise WorkflowTransitionError(
                f"Workflow {state.session_id} has invalid route history."
            )

        if len(history) == len(route):
            return None

        return route[len(history)]

    @staticmethod
    def _require_active(
        state: WorkflowState,
    ) -> None:
        if state.status is not WorkflowStatus.ACTIVE:
            raise WorkflowTransitionError(
                f"Workflow {state.session_id} is "
                f"{state.status.value} and cannot be modified."
            )
