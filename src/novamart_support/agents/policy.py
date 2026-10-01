"""Strands PolicyAgent and its tool binding."""

from typing import Any

from strands import Agent, tool
from strands.models import BedrockModel, Model

from novamart_support.config import Settings
from novamart_support.tools import PolicyToolHandlers

POLICY_SYSTEM_PROMPT = """
You are NovaMart's PolicyAgent.

Your responsibility is limited to retrieving and interpreting grounded
NovaMart policy evidence through the policy search tool provided to you.

Rules:
- Use the policy search tool for policy facts. Never invent policy content.
- Base interpretations only on evidence returned by the tool.
- Respect the evidence source and policy domain returned by retrieval.
- If retrieval is partial, preserve that limitation instead of implying that
  every policy source was successfully searched.
- If no usable evidence is available, do not guess.
- Do not retrieve or reason about customer-specific order facts.
- Do not determine refund eligibility.
- Do not approve or reject refunds.
- Do not modify orders, customers, or workflow records.
- Do not create the final customer-facing support response.
- Keep policy interpretation separate from customer-specific business
  decisions made by other agents.

Your output is grounded policy context for other NovaMart agents.
""".strip()


def build_policy_tools(
    handlers: PolicyToolHandlers,
) -> list[Any]:
    """Bind framework-neutral policy handlers to Strands tools."""

    @tool(
        name="search_policies",
        description=(
            "Search NovaMart return, shipping, and warranty policy sources "
            "for grounded evidence relevant to a question. The underlying "
            "policy retrievers run independently and may return partial "
            "results if one source is unavailable."
        ),
    )
    def search_policies(
        query: str,
        limit_per_source: int = 3,
    ) -> dict[str, Any]:
        return dict(
            handlers.search_policies(
                query,
                limit_per_source=limit_per_source,
            )
        )

    return [search_policies]


def build_policy_agent(
    handlers: PolicyToolHandlers,
    settings: Settings,
    *,
    model: Model | None = None,
) -> Agent:
    """Construct NovaMart's bounded PolicyAgent."""

    resolved_model = model or BedrockModel(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    return Agent(
        model=resolved_model,
        tools=build_policy_tools(handlers),
        system_prompt=POLICY_SYSTEM_PROMPT,
        name="PolicyAgent",
        description=(
            "Retrieves and interprets grounded NovaMart return, shipping, "
            "and warranty policy evidence."
        ),
    )
