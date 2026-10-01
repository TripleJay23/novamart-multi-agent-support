import pytest
from pydantic import BaseModel

from novamart_support.domain import (
    RequestType,
    WorkflowStatus,
)
from novamart_support.exceptions import AgentExecutionError
from novamart_support.runtime.execution import MultiAgentRuntime
from novamart_support.runtime.outputs import (
    CommunicationAgentOutput,
    InventoryAgentOutput,
    OrchestratorAgentOutput,
    PolicyAgentOutput,
    RefundAgentOutput,
)
from novamart_support.services.workflow import (
    COMMUNICATION_AGENT,
    INVENTORY_AGENT,
    POLICY_AGENT,
    REFUND_AGENT,
    WorkflowService,
)
from novamart_support.state import InMemoryWorkflowStateRepository


class FakeResult:
    def __init__(
        self,
        structured_output: BaseModel | None,
    ) -> None:
        self.structured_output = structured_output


class FixedAgent:
    def __init__(
        self,
        output: BaseModel | Exception,
    ) -> None:
        self.output = output
        self.prompts: list[str] = []

    def __call__(
        self,
        prompt: str,
        *,
        structured_output_model: type[BaseModel],
    ) -> FakeResult:
        self.prompts.append(prompt)

        if isinstance(
            self.output,
            Exception,
        ):
            raise self.output

        return FakeResult(
            self.output
        )


class StartingOrchestrator:
    def __init__(
        self,
        service: WorkflowService,
        *,
        session_id: str,
        query: str,
        request_type: RequestType,
        customer_id: str | None = None,
    ) -> None:
        self._service = service
        self._session_id = session_id
        self._query = query
        self._request_type = request_type
        self._customer_id = customer_id
        self.prompts: list[str] = []

    def __call__(
        self,
        prompt: str,
        *,
        structured_output_model: type[BaseModel],
    ) -> FakeResult:
        self.prompts.append(prompt)

        assert (
            structured_output_model
            is OrchestratorAgentOutput
        )

        state = self._service.create_workflow(
            self._session_id,
            self._query,
            self._request_type,
            customer_id=self._customer_id,
        )

        return FakeResult(
            OrchestratorAgentOutput(
                session_id=state.session_id,
                request_type=state.request_type,
                next_agent=self._service.next_agent(
                    state.session_id
                ),
            )
        )


def build_service() -> WorkflowService:
    return WorkflowService(
        InMemoryWorkflowStateRepository()
    )


def test_return_refund_executes_required_agents_in_order() -> None:
    service = build_service()

    orchestrator = StartingOrchestrator(
        service,
        session_id="session-001",
        query="Can I return order ORD-001?",
        request_type=RequestType.RETURN_REFUND,
        customer_id="CUST-001",
    )

    inventory = FixedAgent(
        InventoryAgentOutput(
            context={
                "order_id": "ORD-001",
                "status": "delivered",
                "tier": "premium",
            }
        )
    )
    policy = FixedAgent(
        PolicyAgentOutput(
            context={
                "unused": True,
            }
        )
    )
    refund = FixedAgent(
        RefundAgentOutput(
            context={
                "eligible": True,
                "refund_amount": "149.99",
            }
        )
    )
    communication = FixedAgent(
        CommunicationAgentOutput(
            final_response=(
                "Your order is eligible for return."
            )
        )
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=orchestrator,
        inventory_agent=inventory,
        policy_agent=policy,
        refund_agent=refund,
        communication_agent=communication,
    )

    state = runtime.run(
        "session-001",
        "Can I return order ORD-001?",
        customer_id="CUST-001",
    )

    assert state.status is WorkflowStatus.COMPLETED
    assert state.route_history == [
        INVENTORY_AGENT,
        REFUND_AGENT,
        COMMUNICATION_AGENT,
    ]
    assert state.inventory_context is not None
    assert state.refund_context is not None
    assert state.policy_context is None
    assert state.final_response == (
        "Your order is eligible for return."
    )

    assert len(orchestrator.prompts) == 1
    assert len(inventory.prompts) == 1
    assert len(refund.prompts) == 1
    assert len(communication.prompts) == 1
    assert policy.prompts == []


def test_policy_request_executes_only_policy_then_communication() -> None:
    service = build_service()

    orchestrator = StartingOrchestrator(
        service,
        session_id="session-policy",
        query="What is NovaMart's warranty policy?",
        request_type=RequestType.POLICY,
    )

    inventory = FixedAgent(
        InventoryAgentOutput(
            context={"unused": True}
        )
    )
    policy = FixedAgent(
        PolicyAgentOutput(
            context={
                "evidence": [
                    "Grounded warranty evidence."
                ]
            }
        )
    )
    refund = FixedAgent(
        RefundAgentOutput(
            context={"unused": True}
        )
    )
    communication = FixedAgent(
        CommunicationAgentOutput(
            final_response=(
                "Here is the applicable warranty information."
            )
        )
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=orchestrator,
        inventory_agent=inventory,
        policy_agent=policy,
        refund_agent=refund,
        communication_agent=communication,
    )

    state = runtime.run(
        "session-policy",
        "What is NovaMart's warranty policy?",
    )

    assert state.status is WorkflowStatus.COMPLETED
    assert state.route_history == [
        POLICY_AGENT,
        COMMUNICATION_AGENT,
    ]
    assert state.policy_context is not None

    assert inventory.prompts == []
    assert len(policy.prompts) == 1
    assert refund.prompts == []
    assert len(communication.prompts) == 1


def test_resume_continues_from_persisted_next_agent() -> None:
    service = build_service()

    service.create_workflow(
        "session-resume",
        "Can I return order ORD-001?",
        RequestType.RETURN_REFUND,
        customer_id="CUST-001",
    )
    service.record_inventory_context(
        "session-resume",
        {
            "order_id": "ORD-001",
            "status": "delivered",
        },
    )

    orchestrator = FixedAgent(
        OrchestratorAgentOutput(
            session_id="unused",
            request_type=RequestType.GENERAL,
            next_agent=COMMUNICATION_AGENT,
        )
    )
    inventory = FixedAgent(
        InventoryAgentOutput(
            context={"unused": True}
        )
    )
    policy = FixedAgent(
        PolicyAgentOutput(
            context={"unused": True}
        )
    )
    refund = FixedAgent(
        RefundAgentOutput(
            context={
                "eligible": True,
                "refund_amount": "149.99",
            }
        )
    )
    communication = FixedAgent(
        CommunicationAgentOutput(
            final_response="The order is eligible."
        )
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=orchestrator,
        inventory_agent=inventory,
        policy_agent=policy,
        refund_agent=refund,
        communication_agent=communication,
    )

    state = runtime.resume(
        "session-resume"
    )

    assert state.status is WorkflowStatus.COMPLETED
    assert state.route_history == [
        INVENTORY_AGENT,
        REFUND_AGENT,
        COMMUNICATION_AGENT,
    ]

    assert orchestrator.prompts == []
    assert inventory.prompts == []
    assert len(refund.prompts) == 1
    assert len(communication.prompts) == 1


def test_agent_failure_marks_active_workflow_failed() -> None:
    service = build_service()

    orchestrator = StartingOrchestrator(
        service,
        session_id="session-failed",
        query="Where is order ORD-001?",
        request_type=RequestType.ORDER,
        customer_id="CUST-001",
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=orchestrator,
        inventory_agent=FixedAgent(
            RuntimeError("model failure")
        ),
        policy_agent=FixedAgent(
            PolicyAgentOutput(
                context={"unused": True}
            )
        ),
        refund_agent=FixedAgent(
            RefundAgentOutput(
                context={"unused": True}
            )
        ),
        communication_agent=FixedAgent(
            CommunicationAgentOutput(
                final_response="unused"
            )
        ),
    )

    with pytest.raises(
        AgentExecutionError,
        match="Multi-agent execution failed",
    ):
        runtime.run(
            "session-failed",
            "Where is order ORD-001?",
            customer_id="CUST-001",
        )

    state = service.get_workflow(
        "session-failed"
    )

    assert state.status is WorkflowStatus.FAILED
    assert state.route_history == []


def test_wrong_structured_output_is_rejected_and_workflow_fails() -> None:
    service = build_service()

    orchestrator = StartingOrchestrator(
        service,
        session_id="session-invalid-output",
        query="Where is order ORD-001?",
        request_type=RequestType.ORDER,
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=orchestrator,
        inventory_agent=FixedAgent(
            PolicyAgentOutput(
                context={
                    "wrong": "output type",
                }
            )
        ),
        policy_agent=FixedAgent(
            PolicyAgentOutput(
                context={"unused": True}
            )
        ),
        refund_agent=FixedAgent(
            RefundAgentOutput(
                context={"unused": True}
            )
        ),
        communication_agent=FixedAgent(
            CommunicationAgentOutput(
                final_response="unused"
            )
        ),
    )

    with pytest.raises(
        AgentExecutionError,
        match="InventoryAgentOutput",
    ):
        runtime.run(
            "session-invalid-output",
            "Where is order ORD-001?",
        )

    assert (
        service.get_workflow(
            "session-invalid-output"
        ).status
        is WorkflowStatus.FAILED
    )


def test_existing_session_requires_resume_without_mutating_state() -> None:
    service = build_service()

    original = service.create_workflow(
        "session-existing",
        "Hello.",
        RequestType.GENERAL,
    )

    runtime = MultiAgentRuntime(
        service,
        orchestrator_agent=FixedAgent(
            OrchestratorAgentOutput(
                session_id="unused",
                request_type=RequestType.GENERAL,
                next_agent=COMMUNICATION_AGENT,
            )
        ),
        inventory_agent=FixedAgent(
            InventoryAgentOutput(
                context={"unused": True}
            )
        ),
        policy_agent=FixedAgent(
            PolicyAgentOutput(
                context={"unused": True}
            )
        ),
        refund_agent=FixedAgent(
            RefundAgentOutput(
                context={"unused": True}
            )
        ),
        communication_agent=FixedAgent(
            CommunicationAgentOutput(
                final_response="unused"
            )
        ),
    )

    with pytest.raises(
        AgentExecutionError,
        match=r"Use resume\(\) instead",
    ):
        runtime.run(
            "session-existing",
            "Hello.",
        )

    current = service.get_workflow(
        "session-existing"
    )

    assert current.status is WorkflowStatus.ACTIVE
    assert current.version == original.version
    assert current.route_history == []
