"""Typed outputs exchanged between Strands agents and the runtime."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from novamart_support.domain import RequestType

AgentName = Literal[
    "InventoryAgent",
    "PolicyAgent",
    "RefundAgent",
    "CommunicationAgent",
]


class RuntimeOutput(BaseModel):
    """Base contract for runtime-consumed agent outputs."""

    model_config = ConfigDict(extra="forbid")


class OrchestratorAgentOutput(RuntimeOutput):
    """Validated result after the orchestrator starts a workflow."""

    session_id: str
    request_type: RequestType
    next_agent: AgentName | None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "session_id must not be empty."
            )

        return cleaned


class SpecialistContextOutput(RuntimeOutput):
    """Base contract for specialist-produced workflow context."""

    context: dict[str, Any]

    @field_validator("context")
    @classmethod
    def validate_context(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        if not value:
            raise ValueError(
                "specialist context must not be empty."
            )

        return value


class InventoryAgentOutput(SpecialistContextOutput):
    """InventoryAgent context accepted by the runtime."""


class PolicyAgentOutput(SpecialistContextOutput):
    """PolicyAgent context accepted by the runtime."""


class RefundAgentOutput(SpecialistContextOutput):
    """RefundAgent context accepted by the runtime."""


class CommunicationAgentOutput(RuntimeOutput):
    """Final customer-facing response produced by CommunicationAgent."""

    final_response: str

    @field_validator("final_response")
    @classmethod
    def validate_final_response(
        cls,
        value: str,
    ) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError(
                "final_response must not be empty."
            )

        return cleaned
