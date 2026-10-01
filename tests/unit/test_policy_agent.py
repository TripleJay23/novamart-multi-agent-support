from unittest.mock import patch

import boto3
from strands.models import BedrockModel

from novamart_support.agents import (
    POLICY_SYSTEM_PROMPT,
    build_policy_agent,
    build_policy_tools,
)
from novamart_support.config import Settings
from novamart_support.domain import PolicyEvidence, PolicyType
from novamart_support.services import PolicyService
from novamart_support.tools import PolicyToolHandlers


class FakePolicyRetriever:
    def __init__(
        self,
        policy_type: PolicyType,
        evidence: list[PolicyEvidence],
    ) -> None:
        self._policy_type = policy_type
        self._evidence = evidence

    @property
    def policy_type(self) -> PolicyType:
        return self._policy_type

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        return self._evidence[:limit]


def build_handlers() -> PolicyToolHandlers:
    retrievers = [
        FakePolicyRetriever(
            PolicyType.RETURNS,
            [
                PolicyEvidence(
                    policy_type=PolicyType.RETURNS,
                    content="Premium customers have an extended return window.",
                    source="returns-kb",
                    relevance_score=0.95,
                )
            ],
        ),
        FakePolicyRetriever(
            PolicyType.SHIPPING,
            [
                PolicyEvidence(
                    policy_type=PolicyType.SHIPPING,
                    content="Standard shipping timing depends on destination.",
                    source="shipping-kb",
                    relevance_score=0.85,
                )
            ],
        ),
        FakePolicyRetriever(
            PolicyType.WARRANTY,
            [
                PolicyEvidence(
                    policy_type=PolicyType.WARRANTY,
                    content="Warranty coverage depends on product category.",
                    source="warranty-kb",
                    relevance_score=0.80,
                )
            ],
        ),
    ]

    return PolicyToolHandlers(
        PolicyService(retrievers)
    )


def build_offline_model() -> BedrockModel:
    session = boto3.Session(
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
        aws_session_token="testing",
        region_name="us-east-1",
    )

    return BedrockModel(
        boto_session=session,
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


def build_settings() -> Settings:
    return Settings(
        _env_file=None,
        AWS_REGION="us-east-1",
        WORKER_MODEL_ID="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    )


def test_policy_tool_has_expected_contract() -> None:
    tools = build_policy_tools(build_handlers())

    assert len(tools) == 1
    assert tools[0].tool_name == "search_policies"
    assert tools[0].tool_spec


def test_policy_agent_registers_only_policy_tool() -> None:
    model = build_offline_model()

    agent = build_policy_agent(
        build_handlers(),
        build_settings(),
        model=model,
    )

    assert agent.name == "PolicyAgent"
    assert agent.model is model

    assert set(agent.tool_registry.registry) == {
        "search_policies",
    }


def test_policy_agent_prompt_enforces_grounding_boundary() -> None:
    prompt = POLICY_SYSTEM_PROMPT.casefold()

    assert "never invent policy content" in prompt
    assert "only on evidence returned" in prompt
    assert "if no usable evidence is available" in prompt


def test_policy_agent_prompt_preserves_role_boundaries() -> None:
    prompt = POLICY_SYSTEM_PROMPT.casefold()

    assert "do not determine refund eligibility" in prompt
    assert "do not modify orders" in prompt
    assert "do not create the final customer-facing" in prompt
    assert "if retrieval is partial" in prompt


def test_policy_agent_constructs_worker_bedrock_model() -> None:
    injected_model = build_offline_model()
    settings = build_settings()

    with patch(
        "novamart_support.agents.policy.BedrockModel",
        return_value=injected_model,
    ) as model_factory:
        agent = build_policy_agent(
            build_handlers(),
            settings,
        )

    model_factory.assert_called_once_with(
        model_id=settings.worker_model_id,
        region_name=settings.aws_region,
        temperature=0.1,
    )

    assert agent.model is injected_model
