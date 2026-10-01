"""Core domain models for NovaMart customer-support workflows."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)


class RequestType(StrEnum):
    """High-level customer request classification."""

    ORDER = "order"
    RETURN_REFUND = "return_refund"
    POLICY = "policy"
    ACCOUNT = "account"
    CALCULATION = "calculation"
    GENERAL = "general"


class WorkflowStatus(StrEnum):
    """Lifecycle status of a support workflow."""

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowState(BaseModel):
    """Shared state passed between the orchestrator and specialist agents."""

    session_id: str
    customer_id: str | None = None
    original_query: str

    request_type: RequestType = RequestType.GENERAL
    status: WorkflowStatus = WorkflowStatus.ACTIVE

    route_history: list[str] = Field(default_factory=list)

    inventory_context: dict[str, Any] | None = None
    policy_context: dict[str, Any] | None = None
    refund_context: dict[str, Any] | None = None

    final_response: str | None = None

    version: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
