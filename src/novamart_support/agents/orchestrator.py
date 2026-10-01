"""Strands OrchestratorAgent and its workflow-control bindings."""

from typing import Any, Literal

from strands import Agent, tool
from strands.models import BedrockModel, Model

from novamart_support.config import Settings
from novamart_support.tools import OrchestratorToolHandlers

RequestTypeValue = Literal[
    "order",
    "return_refund",
    "policy",
    "account",
    "calculation",
    "general",
]


ORCHESTRATOR_SYSTEM_PROMPT = """
You are NovaMart's OrchestratorAgent.

Your responsibility is to classify support requests and establish or inspect
their workflow routing. You do not decide the route sequence yourself.

Classify each new request into exactly one request type:

- order:
  Questions about a specific order, order status, delivery status, or order
  details.

- return_refund:
  Customer-specific requests about returning an order, refund eligibility,
  or obtaining a refund.

- policy:
  General questions about NovaMart return, shipping, or warranty policy that
  do not themselves require a customer-specific eligibility decision.

- account:
  Requests about a customer's profile, membership tier, or order history.

- calculation:
  Standalone arithmetic requests that do not require customer, order, or
  policy lookup.

- general:
  Greetings or support requests that do not belong to another category.

Rules:
- For a new request, choose exactly one request type and call start_workflow.
- Pass the customer's complete original query without rewriting its meaning.
- Pass customer_id only when it is actually known.
- Treat next_agent returned by the workflow tool as authoritative.
- For an existing workflow, use get_next_agent to recover the legal next step.
- Never invent, reorder, skip, or override workflow routing.
- Never make refund eligibility or policy decisions.
- Never invent customer or order facts.
- Never mutate customer or order data.
- Do not produce the final customer-facing answer.
- If a workflow tool reports an error, preserve the error instead of guessing.
- When a request contains multiple ideas, classify by the primary support
  action required to resolve the customer's request.

Workflow legality is controlled by the deterministic workflow service, not by
your own reasoning.
""".strip()


def build_orchestrator_tools(
    handlers: OrchestratorToolHandlers,
) -> list[Any]:
    """Bind bounded workflow controls to Strands."""

    @tool(
        name="start_workflow",
        description=(
            "Create a NovaMart support workflow after classifying the "
            "customer's request. Returns the deterministic legal next agent."
        ),
    )
    def start_workflow(
        session_id: str,
        original_query: str,
        request_type: RequestTypeValue,
        customer_id: str | None = None,
    ) -> dict[str, Any]:
        return dict(
            handlers.start_workflow(
                session_id,
                original_query,
                request_type,
                customer_id=customer_id,
            )
        )

    @tool(
        name="get_next_agent",
        description=(
            "Retrieve the authoritative next legal agent for an existing "
            "NovaMart support workflow."
        ),
    )
    def get_next_agent(
        session_id: str,
    ) -> dict[str, Any]:
        return dict(
            handlers.get_next_agent(session_id)
        )

    return [
        start_workflow,
        get_next_agent,
    ]


def build_orchestrator_agent(
    handlers: OrchestratorToolHandlers,
    settings: Settings,
    *,
    model: Model | None = None,
) -> Agent:
    """Construct NovaMart's bounded OrchestratorAgent."""

    resolved_model = model or BedrockModel(
        model_id=settings.orchestrator_model_id,
        region_name=settings.aws_region,
        temperature=0.0,
    )

    return Agent(
        model=resolved_model,
        tools=build_orchestrator_tools(handlers),
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        name="OrchestratorAgent",
        description=(
            "Classifies NovaMart customer-support requests and obtains "
            "deterministic workflow routing."
        ),
    )
