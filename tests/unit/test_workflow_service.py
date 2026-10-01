import pytest

from novamart_support.domain import RequestType, WorkflowStatus
from novamart_support.exceptions import WorkflowTransitionError
from novamart_support.services.workflow import (
    COMMUNICATION_AGENT,
    INVENTORY_AGENT,
    POLICY_AGENT,
    REFUND_AGENT,
    WorkflowService,
)
from novamart_support.state import InMemoryWorkflowStateRepository


def build_service() -> WorkflowService:
    return WorkflowService(
        InMemoryWorkflowStateRepository()
    )


@pytest.mark.parametrize(
    ("request_type", "expected_route"),
    [
        (
            RequestType.ORDER,
            (INVENTORY_AGENT, COMMUNICATION_AGENT),
        ),
        (
            RequestType.RETURN_REFUND,
            (
                INVENTORY_AGENT,
                REFUND_AGENT,
                COMMUNICATION_AGENT,
            ),
        ),
        (
            RequestType.POLICY,
            (POLICY_AGENT, COMMUNICATION_AGENT),
        ),
        (
            RequestType.ACCOUNT,
            (INVENTORY_AGENT, COMMUNICATION_AGENT),
        ),
        (
            RequestType.CALCULATION,
            (COMMUNICATION_AGENT,),
        ),
        (
            RequestType.GENERAL,
            (COMMUNICATION_AGENT,),
        ),
    ],
)
def test_every_request_type_has_deterministic_route(
    request_type: RequestType,
    expected_route: tuple[str, ...],
) -> None:
    service = build_service()

    route = service.planned_route(request_type)

    assert route == expected_route
    assert route[-1] == COMMUNICATION_AGENT


def test_create_workflow_normalizes_input_and_sets_route() -> None:
    service = build_service()

    state = service.create_workflow(
        " session-001 ",
        " Where is my order? ",
        RequestType.ORDER,
        customer_id=" CUST-001 ",
    )

    assert state.session_id == "session-001"
    assert state.customer_id == "CUST-001"
    assert state.original_query == "Where is my order?"
    assert state.status is WorkflowStatus.ACTIVE
    assert state.version == 0

    assert service.next_agent("session-001") == INVENTORY_AGENT


def test_return_refund_flow_advances_in_required_order() -> None:
    service = build_service()

    service.create_workflow(
        "session-001",
        "Can I return order ORD-001?",
        RequestType.RETURN_REFUND,
        customer_id="CUST-001",
    )

    inventory_state = service.record_inventory_context(
        "session-001",
        {
            "order_id": "ORD-001",
            "status": "delivered",
            "tier": "premium",
        },
    )

    assert inventory_state.route_history == [INVENTORY_AGENT]
    assert inventory_state.version == 1
    assert service.next_agent("session-001") == REFUND_AGENT

    refund_state = service.record_refund_context(
        "session-001",
        {
            "eligible": True,
            "refund_amount": "149.99",
        },
    )

    assert refund_state.route_history == [
        INVENTORY_AGENT,
        REFUND_AGENT,
    ]
    assert refund_state.version == 2
    assert service.next_agent("session-001") == COMMUNICATION_AGENT

    completed = service.complete(
        "session-001",
        "Your order is eligible for return.",
    )

    assert completed.status is WorkflowStatus.COMPLETED
    assert completed.final_response == (
        "Your order is eligible for return."
    )
    assert completed.route_history == [
        INVENTORY_AGENT,
        REFUND_AGENT,
        COMMUNICATION_AGENT,
    ]
    assert completed.version == 3
    assert service.next_agent("session-001") is None


def test_policy_flow_persists_only_policy_context() -> None:
    service = build_service()

    service.create_workflow(
        "session-policy",
        "What is the warranty policy?",
        RequestType.POLICY,
    )

    state = service.record_policy_context(
        "session-policy",
        {
            "evidence": [
                {
                    "policy_type": "warranty",
                    "content": "Grounded warranty evidence.",
                }
            ]
        },
    )

    assert state.policy_context is not None
    assert state.inventory_context is None
    assert state.refund_context is None
    assert state.route_history == [POLICY_AGENT]
    assert service.next_agent("session-policy") == COMMUNICATION_AGENT


def test_out_of_order_specialist_is_rejected() -> None:
    service = build_service()

    service.create_workflow(
        "session-001",
        "Can I return this?",
        RequestType.RETURN_REFUND,
    )

    with pytest.raises(
        WorkflowTransitionError,
        match="expected InventoryAgent, not RefundAgent",
    ):
        service.record_refund_context(
            "session-001",
            {"eligible": True},
        )


def test_wrong_specialist_for_request_type_is_rejected() -> None:
    service = build_service()

    service.create_workflow(
        "session-policy",
        "What is your shipping policy?",
        RequestType.POLICY,
    )

    with pytest.raises(
        WorkflowTransitionError,
        match="expected PolicyAgent, not InventoryAgent",
    ):
        service.record_inventory_context(
            "session-policy",
            {"customer_id": "CUST-001"},
        )


def test_workflow_cannot_complete_before_required_specialists() -> None:
    service = build_service()

    service.create_workflow(
        "session-001",
        "Can I return this order?",
        RequestType.RETURN_REFUND,
    )

    with pytest.raises(
        WorkflowTransitionError,
        match="cannot complete yet",
    ):
        service.complete(
            "session-001",
            "Final response.",
        )


def test_general_workflow_can_go_directly_to_communication() -> None:
    service = build_service()

    service.create_workflow(
        "session-general",
        "Hello, I need some help.",
        RequestType.GENERAL,
    )

    assert (
        service.next_agent("session-general")
        == COMMUNICATION_AGENT
    )

    completed = service.complete(
        "session-general",
        "Hello! How can NovaMart help you today?",
    )

    assert completed.status is WorkflowStatus.COMPLETED
    assert completed.route_history == [COMMUNICATION_AGENT]


def test_completed_workflow_cannot_be_modified() -> None:
    service = build_service()

    service.create_workflow(
        "session-policy",
        "What is your return policy?",
        RequestType.POLICY,
    )

    service.record_policy_context(
        "session-policy",
        {"evidence": ["Grounded policy evidence."]},
    )

    service.complete(
        "session-policy",
        "Here is the applicable return-policy information.",
    )

    with pytest.raises(
        WorkflowTransitionError,
        match="completed and cannot be modified",
    ):
        service.record_policy_context(
            "session-policy",
            {"evidence": ["Different evidence."]},
        )


def test_failed_workflow_is_terminal() -> None:
    service = build_service()

    service.create_workflow(
        "session-failed",
        "Where is my order?",
        RequestType.ORDER,
    )

    failed = service.mark_failed("session-failed")

    assert failed.status is WorkflowStatus.FAILED
    assert failed.version == 1
    assert service.next_agent("session-failed") is None

    with pytest.raises(
        WorkflowTransitionError,
        match="failed and cannot be modified",
    ):
        service.record_inventory_context(
            "session-failed",
            {"order_id": "ORD-001"},
        )


def test_empty_specialist_context_is_rejected() -> None:
    service = build_service()

    service.create_workflow(
        "session-order",
        "Where is my order?",
        RequestType.ORDER,
    )

    with pytest.raises(
        ValueError,
        match="specialist context must not be empty",
    ):
        service.record_inventory_context(
            "session-order",
            {},
        )
