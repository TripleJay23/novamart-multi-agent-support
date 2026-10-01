"""Business entities used by NovaMart support agents."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CustomerTier(StrEnum):
    STANDARD = "standard"
    PREMIUM = "premium"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PolicyType(StrEnum):
    RETURNS = "returns"
    SHIPPING = "shipping"
    WARRANTY = "warranty"


class Customer(BaseModel):
    customer_id: str
    name: str
    tier: CustomerTier = CustomerTier.STANDARD
    email: str | None = None


class Order(BaseModel):
    order_id: str
    customer_id: str
    product_name: str
    category: str
    unit_price: Decimal = Field(ge=0)
    quantity: int = Field(default=1, ge=1)

    status: OrderStatus
    ordered_at: datetime
    delivered_at: datetime | None = None

    return_eligible: bool = False


class PolicyEvidence(BaseModel):
    policy_type: PolicyType
    content: str
    source: str
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RefundDecision(BaseModel):
    eligible: bool
    reason: str
    refund_amount: Decimal | None = Field(default=None, ge=0)
    order_id: str | None = None


class RetrieverFailure(BaseModel):
    """Failure from one policy retrieval source."""

    policy_type: PolicyType
    message: str


class PolicySearchResult(BaseModel):
    """Combined result from parallel policy retrieval."""

    query: str
    evidence: list[PolicyEvidence]
    failures: list[RetrieverFailure] = Field(default_factory=list)

    @property
    def is_partial(self) -> bool:
        """Whether one or more retrievers failed."""

        return bool(self.failures)
