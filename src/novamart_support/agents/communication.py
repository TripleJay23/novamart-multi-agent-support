"""Strands CommunicationAgent and its tool binding."""

from typing import Any

from strands import Agent, tool
from strands.models import BedrockModel, Model

from novamart_support.config import Settings
from novamart_support.tools import CommunicationToolHandlers

COMMUNICATION_SYSTEM_PROMPT = """
You are NovaMart's CommunicationAgent.

You are the only specialist agent responsible for composing the final
customer-facing response.

Before composing a response, use the workflow-context tool to retrieve the
facts and decisions already collected for the session.

Rules:
- Base the response only on the customer's original query and the workflow
  context returned by the tool.
- Never invent customer, order, policy, refund, delivery, warranty, shipping,
  or eligibility facts.
- Do not make new refund, policy, or business-rule decisions.
- Do not change or reinterpret deterministic decisions made upstream.
- If required information is missing or retrieval was partial, communicate
  that limitation clearly rather than guessing.
- Do not claim that a refund, payment, return label, shipment, or other action
  was completed unless the workflow context explicitly proves it.
- Do not expose internal agent names, routing history, tool names, prompts,
  knowledge-base identifiers, database details, or internal reasoning.
- Do not modify workflow state, customer records, or orders.
- Produce a clear, professional, concise response appropriate for the
  customer.

Your output is the final customer-facing support response.
""".strip()


def build_communication_tools(
    handlers: CommunicationToolHandlers,
) -> list[Any]:
    """Bind communication workflow-context access to Strands."""

    @tool(
        name="get_workflow_context",
        description=(
            "Retrieve the accumulated NovaMart workflow context for a support "
            "session, including the original query and any inventory, policy, "
            "or refund context produced by specialist agents."
        ),
    )
    def get_workflow_context(
        session_id: str,
    ) -> dict[str, Any]:
        return dict(
            handlers.get_workflow_context(session_id)
        )

    return [get_workflow_context]


def build_communication_agent(
    handlers: CommunicationToolHandlers,
    settings: Settings,
    *,
    model: Model | None = None,
) -> Agent:
    """Construct NovaMart's final-response CommunicationAgent."""

    resolved_model = model or BedrockModel(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    return Agent(
        model=resolved_model,
        tools=build_communication_tools(handlers),
        system_prompt=COMMUNICATION_SYSTEM_PROMPT,
        name="CommunicationAgent",
        description=(
            "Composes the final customer-facing response from already "
            "validated NovaMart workflow context."
        ),
    )
