"""Developer-facing summaries without internal specialist context objects."""

from novamart_support.domain import WorkflowState


def workflow_summary(state: WorkflowState) -> dict[str, object]:
    """Return a JSON-compatible summary shared by local and hosted entrypoints."""

    return {
        "session_id": state.session_id,
        "customer_id": state.customer_id,
        "request_type": state.request_type.value,
        "status": state.status.value,
        "route_history": list(state.route_history),
        "final_response": state.final_response,
        "version": state.version,
    }
