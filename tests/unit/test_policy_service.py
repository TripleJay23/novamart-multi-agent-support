from threading import Barrier, current_thread

import pytest

from novamart_support.domain import (
    PolicyEvidence,
    PolicyType,
)
from novamart_support.exceptions import PolicyRetrievalError
from novamart_support.services import PolicyService


class FakeRetriever:
    def __init__(
        self,
        policy_type: PolicyType,
        evidence: list[PolicyEvidence] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._policy_type = policy_type
        self._evidence = evidence or []
        self._error = error
        self.received_query: str | None = None
        self.received_limit: int | None = None

    @property
    def policy_type(self) -> PolicyType:
        return self._policy_type

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        self.received_query = query
        self.received_limit = limit

        if self._error is not None:
            raise self._error

        return list(self._evidence)


class BarrierRetriever:
    def __init__(
        self,
        policy_type: PolicyType,
        barrier: Barrier,
    ) -> None:
        self._policy_type = policy_type
        self._barrier = barrier
        self.thread_name: str | None = None

    @property
    def policy_type(self) -> PolicyType:
        return self._policy_type

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        self.thread_name = current_thread().name

        self._barrier.wait(timeout=2)

        return [
            PolicyEvidence(
                policy_type=self.policy_type,
                content=f"{self.policy_type.value} policy",
                source=f"{self.policy_type.value}-kb",
                relevance_score=0.8,
            )
        ]


def evidence(
    policy_type: PolicyType,
    content: str,
    source: str,
    score: float | None,
) -> PolicyEvidence:
    return PolicyEvidence(
        policy_type=policy_type,
        content=content,
        source=source,
        relevance_score=score,
    )


def test_search_merges_and_ranks_evidence() -> None:
    service = PolicyService(
        [
            FakeRetriever(
                PolicyType.RETURNS,
                [
                    evidence(
                        PolicyType.RETURNS,
                        "Returns evidence",
                        "returns-kb",
                        0.95,
                    )
                ],
            ),
            FakeRetriever(
                PolicyType.SHIPPING,
                [
                    evidence(
                        PolicyType.SHIPPING,
                        "Shipping evidence",
                        "shipping-kb",
                        0.75,
                    )
                ],
            ),
            FakeRetriever(
                PolicyType.WARRANTY,
                [
                    evidence(
                        PolicyType.WARRANTY,
                        "Warranty evidence",
                        "warranty-kb",
                        0.85,
                    )
                ],
            ),
        ]
    )

    result = service.search_all("What policy applies?")

    assert [
        item.policy_type
        for item in result.evidence
    ] == [
        PolicyType.RETURNS,
        PolicyType.WARRANTY,
        PolicyType.SHIPPING,
    ]
    assert result.failures == []
    assert result.is_partial is False


def test_duplicate_evidence_keeps_highest_score() -> None:
    duplicate_low = evidence(
        PolicyType.RETURNS,
        "Returns are allowed within the applicable window.",
        "shared-policy",
        0.60,
    )

    duplicate_high = evidence(
        PolicyType.RETURNS,
        "  RETURNS are allowed   within the applicable window. ",
        "SHARED-POLICY",
        0.94,
    )

    service = PolicyService(
        [
            FakeRetriever(
                PolicyType.RETURNS,
                [duplicate_low, duplicate_high],
            )
        ]
    )

    result = service.search_all("returns")

    assert len(result.evidence) == 1
    assert result.evidence[0].relevance_score == 0.94


def test_partial_failure_keeps_successful_evidence() -> None:
    service = PolicyService(
        [
            FakeRetriever(
                PolicyType.RETURNS,
                [
                    evidence(
                        PolicyType.RETURNS,
                        "Return policy",
                        "returns-kb",
                        0.9,
                    )
                ],
            ),
            FakeRetriever(
                PolicyType.SHIPPING,
                error=RuntimeError("shipping KB unavailable"),
            ),
        ]
    )

    result = service.search_all("return policy")

    assert len(result.evidence) == 1
    assert result.is_partial is True
    assert len(result.failures) == 1
    assert result.failures[0].policy_type is PolicyType.SHIPPING


def test_total_retrieval_failure_raises_controlled_error() -> None:
    service = PolicyService(
        [
            FakeRetriever(
                PolicyType.RETURNS,
                error=RuntimeError("returns failed"),
            ),
            FakeRetriever(
                PolicyType.SHIPPING,
                error=RuntimeError("shipping failed"),
            ),
        ]
    )

    with pytest.raises(PolicyRetrievalError):
        service.search_all("policy")


def test_empty_evidence_raises_controlled_error() -> None:
    service = PolicyService(
        [
            FakeRetriever(PolicyType.RETURNS),
        ]
    )

    with pytest.raises(PolicyRetrievalError):
        service.search_all("unknown policy")


def test_mismatched_policy_evidence_isolated_as_failure() -> None:
    service = PolicyService(
        [
            FakeRetriever(
                PolicyType.RETURNS,
                [
                    evidence(
                        PolicyType.SHIPPING,
                        "Incorrectly classified evidence",
                        "bad-retriever",
                        0.8,
                    )
                ],
            ),
            FakeRetriever(
                PolicyType.WARRANTY,
                [
                    evidence(
                        PolicyType.WARRANTY,
                        "Warranty evidence",
                        "warranty-kb",
                        0.7,
                    )
                ],
            ),
        ]
    )

    result = service.search_all("warranty")

    assert len(result.evidence) == 1
    assert result.evidence[0].policy_type is PolicyType.WARRANTY
    assert result.failures[0].policy_type is PolicyType.RETURNS


def test_query_and_limit_are_forwarded() -> None:
    retriever = FakeRetriever(
        PolicyType.RETURNS,
        [
            evidence(
                PolicyType.RETURNS,
                "Return policy",
                "returns-kb",
                0.8,
            )
        ],
    )

    service = PolicyService([retriever])

    service.search_all(
        "  return window  ",
        limit_per_source=7,
    )

    assert retriever.received_query == "return window"
    assert retriever.received_limit == 7


def test_empty_query_is_rejected() -> None:
    service = PolicyService(
        [FakeRetriever(PolicyType.RETURNS)]
    )

    with pytest.raises(ValueError):
        service.search_all("   ")


def test_duplicate_retriever_domains_are_rejected() -> None:
    with pytest.raises(ValueError):
        PolicyService(
            [
                FakeRetriever(PolicyType.RETURNS),
                FakeRetriever(PolicyType.RETURNS),
            ]
        )


def test_retrievers_execute_concurrently() -> None:
    barrier = Barrier(3)

    retrievers = [
        BarrierRetriever(PolicyType.RETURNS, barrier),
        BarrierRetriever(PolicyType.SHIPPING, barrier),
        BarrierRetriever(PolicyType.WARRANTY, barrier),
    ]

    service = PolicyService(retrievers)

    result = service.search_all("What policies apply?")

    assert len(result.evidence) == 3

    thread_names = {
        retriever.thread_name
        for retriever in retrievers
    }

    assert None not in thread_names
    assert len(thread_names) == 3
