"""Policy retrieval contracts."""

from typing import Protocol

from novamart_support.domain import PolicyEvidence, PolicyType


class PolicyRetriever(Protocol):
    """Retrieve evidence from one bounded policy knowledge source."""

    @property
    def policy_type(self) -> PolicyType:
        """Policy domain handled by this retriever."""

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        """Retrieve grounded policy evidence for a query."""
