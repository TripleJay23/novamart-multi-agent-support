"""AgentCore HTTP entrypoint for trusted, IAM-authenticated support callers.

Each invocation gets fresh agent instances. Persisted workflow progress belongs
to the request-context session, never to a caller-selected payload field.
"""

import logging
from typing import Annotated, Literal, Self

from bedrock_agentcore.runtime import BedrockAgentCoreApp, RequestContext
from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from novamart_support.config import get_settings
from novamart_support.domain import WorkflowStatus
from novamart_support.exceptions import (
    AgentExecutionError,
    ConcurrencyConflictError,
    ConfigurationError,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
)
from novamart_support.runtime import build_application
from novamart_support.runtime.summary import workflow_summary

logger = logging.getLogger(__name__)
app = BedrockAgentCoreApp()

Query = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
CustomerId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
SessionId = Annotated[str, StringConstraints(min_length=33, max_length=256, pattern=r"^\S+$")]
_session_adapter = TypeAdapter(SessionId)


class InvocationRequest(BaseModel):
    """One new workflow or continuation of the context's existing workflow."""

    model_config = ConfigDict(extra="forbid", strict=True)

    action: Literal["run", "resume"] = "run"
    query: Query | None = None
    customer_id: CustomerId | None = None

    @model_validator(mode="after")
    def validate_action_fields(self) -> Self:
        if self.action == "run" and self.query is None:
            raise ValueError("run requires a query")
        if self.action == "resume" and {"query", "customer_id"} & self.model_fields_set:
            raise ValueError("resume does not accept query or customer_id")
        return self


def _error(code: str, message: str) -> dict[str, object]:
    return {"ok": False, "error": {"code": code, "message": message}}


def handle_invocation(payload: dict[str, object], context: RequestContext) -> dict[str, object]:
    """Execute a validated request without returning raw exception details."""

    try:
        request = InvocationRequest.model_validate(payload)
        session_id = _session_adapter.validate_python(context.session_id)
    except ValidationError:
        return _error(
            "invalid_request",
            "Provide a valid run or resume request and a 33-256 character runtime session ID.",
        )

    try:
        # Strands agents carry conversation history: never cache this container.
        application = build_application(get_settings())
        if request.action == "run":
            assert request.query is not None  # Enforced by the request contract.
            state = application.runtime.run(
                session_id, request.query, customer_id=request.customer_id,
            )
        else:
            state = application.runtime.resume(session_id)

        return {
            "ok": state.status is not WorkflowStatus.FAILED,
            "workflow": workflow_summary(state),
        }
    except ConfigurationError:
        return _error("configuration_error", "The support service is not configured correctly.")
    except WorkflowNotFoundError:
        return _error("workflow_not_found", "No workflow exists for this session.")
    except WorkflowAlreadyExistsError:
        return _error("workflow_exists", "This session already has a workflow; use resume.")
    except ConcurrencyConflictError:
        return _error("conflict", "The workflow changed during this request; inspect its state.")
    except AgentExecutionError:
        return _error("execution_failed", "The support workflow could not be completed.")
    except Exception as exc:
        # Exception strings and tracebacks may contain prompts or AWS details.
        logger.error("AgentCore invocation failed (%s).", type(exc).__name__)
        return _error("internal_error", "The support service could not process this request.")


app.entrypoint(handle_invocation)


def main() -> None:
    """Serve the SDK's /ping and /invocations endpoints on port 8080."""

    app.run(host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
