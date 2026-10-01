"""Strands InventoryAgent and its tool bindings."""

from typing import Any

from strands import Agent, tool
from strands.models import BedrockModel, Model

from novamart_support.config import Settings
from novamart_support.tools import InventoryToolHandlers

INVENTORY_SYSTEM_PROMPT = """
You are NovaMart's InventoryAgent.

Your responsibility is limited to retrieving factual customer and order
information through the tools provided to you.

Rules:
- Use tools for customer and order facts. Never invent missing data.
- Do not determine refund eligibility.
- Do not interpret return, shipping, or warranty policy.
- Do not approve or reject refunds.
- Do not create the final customer-facing support response.
- Keep retrieved facts precise and clearly separated from assumptions.
- If a tool reports an error or missing record, preserve that result rather
  than guessing.
- For order, return, or refund workflows, retrieve the relevant order facts
  and customer tier when they are needed by downstream agents.

Your output is factual context for other NovaMart agents.
""".strip()


def build_inventory_tools(
    handlers: InventoryToolHandlers,
) -> list[Any]:
    """Bind framework-neutral inventory handlers to Strands tools."""

    @tool(
        name="get_customer_profile",
        description=(
            "Retrieve a customer's basic NovaMart profile and membership tier. "
            "Use this when downstream reasoning requires customer identity or tier."
        ),
    )
    def get_customer_profile(customer_id: str) -> dict[str, Any]:
        return dict(handlers.get_customer_profile(customer_id))

    @tool(
        name="get_order",
        description=(
            "Retrieve factual details for one order belonging to a customer. "
            "Use this for order status, product, price, dates, quantity, and "
            "return-eligibility facts."
        ),
    )
    def get_order(
        customer_id: str,
        order_id: str,
    ) -> dict[str, Any]:
        return dict(
            handlers.get_order(
                customer_id,
                order_id,
            )
        )

    @tool(
        name="list_customer_orders",
        description=(
            "List a customer's NovaMart orders from newest to oldest. "
            "Use this when an order ID is unknown or order history is required."
        ),
    )
    def list_customer_orders(
        customer_id: str,
    ) -> dict[str, Any]:
        return dict(
            handlers.list_customer_orders(customer_id)
        )

    return [
        get_customer_profile,
        get_order,
        list_customer_orders,
    ]


def build_inventory_agent(
    handlers: InventoryToolHandlers,
    settings: Settings,
    *,
    model: Model | None = None,
) -> Agent:
    """Construct NovaMart's bounded InventoryAgent."""

    resolved_model = model or BedrockModel(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    return Agent(
        model=resolved_model,
        tools=build_inventory_tools(handlers),
        system_prompt=INVENTORY_SYSTEM_PROMPT,
        name="InventoryAgent",
        description=(
            "Retrieves factual NovaMart customer and order information "
            "without making policy or refund decisions."
        ),
    )
