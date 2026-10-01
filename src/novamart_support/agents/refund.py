"""Strands RefundAgent and its tool binding."""

from typing import Any

from strands import Agent, tool
from strands.models import BedrockModel, Model

from novamart_support.config import Settings
from novamart_support.tools import RefundToolHandlers

REFUND_SYSTEM_PROMPT = """
You are NovaMart's RefundAgent.

Your responsibility is limited to evaluating refund and return eligibility
using the deterministic refund tool provided to you.

Rules:
- Always use the refund eligibility tool for eligibility decisions.
- Never invent customer, order, delivery, price, or eligibility facts.
- Do not override or reinterpret the deterministic eligibility result.
- Do not invent return, shipping, or warranty policy.
- Do not claim that a refund, payment, return label, or order mutation has
  actually been processed.
- Do not modify orders or customer records.
- Do not create the final customer-facing support response.
- If the tool reports an error or missing record, preserve that result rather
  than guessing.
- Clearly distinguish eligibility evaluation from actual refund processing.

Your output is refund-decision context for other NovaMart agents.
""".strip()


def build_refund_tools(
    handlers: RefundToolHandlers,
) -> list[Any]:
    """Bind framework-neutral refund handlers to Strands tools."""

    @tool(
        name="evaluate_refund",
        description=(
            "Evaluate whether a NovaMart order is eligible for a refund or "
            "return using deterministic business rules. Returns the decision, "
            "reason, order ID, and refund amount when applicable. This tool "
            "does not process or initiate a refund."
        ),
    )
    def evaluate_refund(
        customer_id: str,
        order_id: str,
    ) -> dict[str, Any]:
        return dict(
            handlers.evaluate_refund(
                customer_id,
                order_id,
            )
        )

    return [evaluate_refund]


def build_refund_agent(
    handlers: RefundToolHandlers,
    settings: Settings,
    *,
    model: Model | None = None,
) -> Agent:
    """Construct NovaMart's bounded RefundAgent."""

    resolved_model = model or BedrockModel(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    return Agent(
        model=resolved_model,
        tools=build_refund_tools(handlers),
        system_prompt=REFUND_SYSTEM_PROMPT,
        name="RefundAgent",
        description=(
            "Evaluates refund eligibility using deterministic NovaMart "
            "business rules without processing refunds."
        ),
    )
