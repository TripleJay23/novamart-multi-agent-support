"""Agent-facing workflow orchestration tool handlers."""

from typing import Any

from novamart_support.domain import RequestType, WorkflowState
from novamart_support.exceptions import (
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowTransitionError,
)
from novamart_support.services.workflow import WorkflowService
from novamart_support.tools.result import ToolResponse, failure, success

_ALLOWED_REQUEST_TYPES = ", ".join(
    request_type.value
    for request_type in RequestType
)


class OrchestratorToolHandlers:
    """Expose bounded workflow controls to the orchestrator agent."""

    def __init__(
        self,
        service: WorkflowService,
    ) -> None:
        self._service = service

    def start_workflow(
        self,
        session_id: str,
        original_query: str,
        request_type: str,
        *,
        customer_id: str | None = None,
    ) -> ToolResponse:
        """Create a classified workflow and return its legal first agent."""

        cleaned_request_type = request_type.strip().casefold()

        try:
            classified_type = RequestType(cleaned_request_type)
        except ValueError:
            return failure(
                "invalid_request_type",
                (
                    "request_type must be one of: "
                    f"{_ALLOWED_REQUEST_TYPES}."
                ),
            )

        try:
            state = self._service.create_workflow(
                session_id,
                original_query,
                classified_type,
                customer_id=customer_id,
            )
        except ValueError as exc:
            return failure(
                "invalid_input",
                str(exc),
            )
        except WorkflowAlreadyExistsError as exc:
            return failure(
                "workflow_already_exists",
                str(exc),
            )

        return success(
            self._workflow_summary(
                state,
                next_agent=self._service.next_agent(
                    state.session_id
                ),
            )
        )

    def get_next_agent(
        self,
        session_id: str,
    ) -> ToolResponse:
        """Return the next legal agent for an existing workflow."""

        try:
            state = self._service.get_workflow(session_id)
            next_agent = self._service.next_agent(session_id)
        except ValueError as exc:
            return failure(
                "invalid_input",
                str(exc),
            )
        except WorkflowNotFoundError as exc:
            return failure(
                "workflow_not_found",
                str(exc),
            )
        except WorkflowTransitionError as exc:
            return failure(
                "workflow_transition_error",
                str(exc),
            )

        return success(
            self._workflow_summary(
                state,
                next_agent=next_agent,
            )
        )

    @staticmethod
    def _workflow_summary(
        state: WorkflowState,
        *,
        next_agent: str | None,
    ) -> dict[str, Any]:
        return {
            "session_id": state.session_id,
            "customer_id": state.customer_id,
            "request_type": state.request_type.value,
            "status": state.status.value,
            "route_history": list(state.route_history),
            "next_agent": next_agent,
        }
