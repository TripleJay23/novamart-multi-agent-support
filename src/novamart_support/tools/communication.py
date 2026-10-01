"""Agent-facing communication tool handlers."""

from novamart_support.exceptions import WorkflowNotFoundError
from novamart_support.state.repository import WorkflowStateRepository
from novamart_support.tools.result import ToolResponse, failure, success


class CommunicationToolHandlers:
    """Expose read-only workflow context for final response composition."""

    def __init__(
        self,
        repository: WorkflowStateRepository,
    ) -> None:
        self._repository = repository

    def get_workflow_context(
        self,
        session_id: str,
    ) -> ToolResponse:
        cleaned_session_id = session_id.strip()

        if not cleaned_session_id:
            return failure(
                "invalid_input",
                "session_id must not be empty.",
            )

        try:
            workflow = self._repository.get(cleaned_session_id)
        except WorkflowNotFoundError as exc:
            return failure(
                "workflow_not_found",
                str(exc),
            )

        return success(
            {
                "session_id": workflow.session_id,
                "customer_id": workflow.customer_id,
                "original_query": workflow.original_query,
                "request_type": workflow.request_type.value,
                "status": workflow.status.value,
                "route_history": list(workflow.route_history),
                "inventory_context": workflow.inventory_context,
                "policy_context": workflow.policy_context,
                "refund_context": workflow.refund_context,
            }
        )
