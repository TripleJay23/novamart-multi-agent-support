"""Application composition root.

Infrastructure dependencies are constructed here so agents and domain
services do not need to know how AWS clients or adapters are created.
"""

from dataclasses import dataclass
from typing import Any

from novamart_support.config import Settings
from novamart_support.exceptions import ConfigurationError
from novamart_support.rag import (
    ReturnsPolicyRetriever,
    ShippingPolicyRetriever,
    WarrantyPolicyRetriever,
)
from novamart_support.repositories import (
    DynamoDBCustomerRepository,
    DynamoDBOrderRepository,
)
from novamart_support.services import (
    InventoryService,
    PolicyService,
    RefundService,
)
from novamart_support.state import DynamoDBWorkflowStateRepository


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Constructed application dependencies."""

    workflow_repository: DynamoDBWorkflowStateRepository
    customer_repository: DynamoDBCustomerRepository
    order_repository: DynamoDBOrderRepository
    inventory_service: InventoryService
    refund_service: RefundService
    policy_service: PolicyService


def _required(value: str | None, setting_name: str) -> str:
    if value is None or not value.strip():
        raise ConfigurationError(
            f"Required runtime configuration is missing: {setting_name}"
        )

    return value.strip()


def _optional(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def build_application(
    settings: Settings,
    *,
    dynamodb_client: Any | None = None,
    bedrock_runtime_client: Any | None = None,
) -> ApplicationContainer:
    """Construct the AWS-backed NovaMart application dependency graph."""

    returns_kb_id = _required(
        settings.returns_kb_id,
        "RETURNS_KB_ID",
    )
    shipping_kb_id = _required(
        settings.shipping_kb_id,
        "SHIPPING_KB_ID",
    )
    warranty_kb_id = _required(
        settings.warranty_kb_id,
        "WARRANTY_KB_ID",
    )

    guardrail_id = _optional(settings.guardrail_id)
    guardrail_version = _optional(settings.guardrail_version)

    if bool(guardrail_id) != bool(guardrail_version):
        raise ConfigurationError(
            "GUARDRAIL_ID and GUARDRAIL_VERSION must be configured together."
        )

    workflow_repository = DynamoDBWorkflowStateRepository(
        settings.resolved_workflow_table_name,
        region_name=settings.aws_region,
        dynamodb_client=dynamodb_client,
    )

    customer_repository = DynamoDBCustomerRepository(
        settings.resolved_customer_table_name,
        region_name=settings.aws_region,
        dynamodb_client=dynamodb_client,
    )

    order_repository = DynamoDBOrderRepository(
        settings.resolved_order_table_name,
        region_name=settings.aws_region,
        dynamodb_client=dynamodb_client,
    )

    inventory_service = InventoryService(
        customer_repository,
        order_repository,
    )

    refund_service = RefundService(inventory_service)

    policy_service = PolicyService(
        [
            ReturnsPolicyRetriever(
                returns_kb_id,
                region_name=settings.aws_region,
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
                runtime_client=bedrock_runtime_client,
            ),
            ShippingPolicyRetriever(
                shipping_kb_id,
                region_name=settings.aws_region,
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
                runtime_client=bedrock_runtime_client,
            ),
            WarrantyPolicyRetriever(
                warranty_kb_id,
                region_name=settings.aws_region,
                guardrail_id=guardrail_id,
                guardrail_version=guardrail_version,
                runtime_client=bedrock_runtime_client,
            ),
        ]
    )

    return ApplicationContainer(
        workflow_repository=workflow_repository,
        customer_repository=customer_repository,
        order_repository=order_repository,
        inventory_service=inventory_service,
        refund_service=refund_service,
        policy_service=policy_service,
    )
