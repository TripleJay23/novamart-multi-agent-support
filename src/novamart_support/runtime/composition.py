"""Application composition root.

Infrastructure dependencies are constructed here so agents, tools, and
domain services do not need to know how AWS clients or adapters are created.
"""

from dataclasses import dataclass
from typing import Any

from strands import Agent
from strands.models import Model

from novamart_support.agents import (
    build_communication_agent,
    build_inventory_agent,
    build_orchestrator_agent,
    build_policy_agent,
    build_refund_agent,
)
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
from novamart_support.runtime.execution import MultiAgentRuntime
from novamart_support.services import (
    InventoryService,
    PolicyService,
    RefundService,
    WorkflowService,
)
from novamart_support.state import DynamoDBWorkflowStateRepository
from novamart_support.tools import (
    CommunicationToolHandlers,
    InventoryToolHandlers,
    OrchestratorToolHandlers,
    PolicyToolHandlers,
    RefundToolHandlers,
)


@dataclass(frozen=True, slots=True)
class ApplicationContainer:
    """Constructed NovaMart application dependency graph."""

    workflow_repository: DynamoDBWorkflowStateRepository
    customer_repository: DynamoDBCustomerRepository
    order_repository: DynamoDBOrderRepository

    inventory_service: InventoryService
    refund_service: RefundService
    policy_service: PolicyService
    workflow_service: WorkflowService

    inventory_handlers: InventoryToolHandlers
    refund_handlers: RefundToolHandlers
    policy_handlers: PolicyToolHandlers
    communication_handlers: CommunicationToolHandlers
    orchestrator_handlers: OrchestratorToolHandlers

    inventory_agent: Agent
    refund_agent: Agent
    policy_agent: Agent
    communication_agent: Agent
    orchestrator_agent: Agent

    runtime: MultiAgentRuntime


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
    orchestrator_model: Model | None = None,
    worker_model: Model | None = None,
) -> ApplicationContainer:
    """Construct the complete AWS-backed NovaMart dependency graph."""

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

    refund_service = RefundService(
        inventory_service
    )

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

    workflow_service = WorkflowService(
        workflow_repository
    )

    inventory_handlers = InventoryToolHandlers(
        inventory_service
    )
    refund_handlers = RefundToolHandlers(
        refund_service
    )
    policy_handlers = PolicyToolHandlers(
        policy_service
    )
    communication_handlers = CommunicationToolHandlers(
        workflow_repository
    )
    orchestrator_handlers = OrchestratorToolHandlers(
        workflow_service
    )

    inventory_agent = build_inventory_agent(
        inventory_handlers,
        settings,
        model=worker_model,
    )
    refund_agent = build_refund_agent(
        refund_handlers,
        settings,
        model=worker_model,
    )
    policy_agent = build_policy_agent(
        policy_handlers,
        settings,
        model=worker_model,
    )
    communication_agent = build_communication_agent(
        communication_handlers,
        settings,
        model=worker_model,
    )
    orchestrator_agent = build_orchestrator_agent(
        orchestrator_handlers,
        settings,
        model=orchestrator_model,
    )

    runtime = MultiAgentRuntime(
        workflow_service,
        orchestrator_agent=orchestrator_agent,
        inventory_agent=inventory_agent,
        policy_agent=policy_agent,
        refund_agent=refund_agent,
        communication_agent=communication_agent,
    )

    return ApplicationContainer(
        workflow_repository=workflow_repository,
        customer_repository=customer_repository,
        order_repository=order_repository,
        inventory_service=inventory_service,
        refund_service=refund_service,
        policy_service=policy_service,
        workflow_service=workflow_service,
        inventory_handlers=inventory_handlers,
        refund_handlers=refund_handlers,
        policy_handlers=policy_handlers,
        communication_handlers=communication_handlers,
        orchestrator_handlers=orchestrator_handlers,
        inventory_agent=inventory_agent,
        refund_agent=refund_agent,
        policy_agent=policy_agent,
        communication_agent=communication_agent,
        orchestrator_agent=orchestrator_agent,
        runtime=runtime,
    )
