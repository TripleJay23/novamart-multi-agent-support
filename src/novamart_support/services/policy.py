"""Parallel policy retrieval and evidence aggregation."""

from collections.abc import Iterable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from novamart_support.domain import (
    PolicyEvidence,
    PolicySearchResult,
    PolicyType,
    RetrieverFailure,
)
from novamart_support.exceptions import PolicyRetrievalError
from novamart_support.rag.retriever import PolicyRetriever


class PolicyService:
    """Coordinate independent policy retrievers concurrently."""

    def __init__(self, retrievers: Iterable[PolicyRetriever]) -> None:
        configured = tuple(retrievers)

        if not configured:
            raise ValueError("At least one policy retriever is required.")

        policy_types = [retriever.policy_type for retriever in configured]

        if len(policy_types) != len(set(policy_types)):
            raise ValueError("Only one retriever may be configured per policy type.")

        self._retrievers = configured

    def search_all(
        self,
        query: str,
        *,
        limit_per_source: int = 3,
    ) -> PolicySearchResult:
        """Search all configured policy sources concurrently."""

        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Policy query must not be empty.")

        if limit_per_source < 1:
            raise ValueError("limit_per_source must be at least 1.")

        evidence: list[PolicyEvidence] = []
        failures: list[RetrieverFailure] = []

        with ThreadPoolExecutor(
            max_workers=len(self._retrievers),
            thread_name_prefix="policy-retriever",
        ) as executor:
            futures: dict[Future[list[PolicyEvidence]], PolicyType] = {
                executor.submit(
                    retriever.retrieve,
                    cleaned_query,
                    limit=limit_per_source,
                ): retriever.policy_type
                for retriever in self._retrievers
            }

            for future in as_completed(futures):
                policy_type = futures[future]

                try:
                    retrieved = future.result()

                    if any(
                        item.policy_type is not policy_type
                        for item in retrieved
                    ):
                        raise ValueError(
                            f"{policy_type.value} retriever returned evidence "
                            "for another policy domain."
                        )

                    evidence.extend(retrieved)

                except Exception as exc:
                    failures.append(
                        RetrieverFailure(
                            policy_type=policy_type,
                            message=str(exc),
                        )
                    )

        merged = self._deduplicate_and_rank(evidence)

        if not merged:
            failed_sources = ", ".join(
                failure.policy_type.value
                for failure in sorted(
                    failures,
                    key=lambda item: item.policy_type.value,
                )
            )

            suffix = (
                f" Failed sources: {failed_sources}."
                if failed_sources
                else ""
            )

            raise PolicyRetrievalError(
                f"No usable policy evidence was retrieved.{suffix}"
            )

        return PolicySearchResult(
            query=cleaned_query,
            evidence=merged,
            failures=sorted(
                failures,
                key=lambda item: item.policy_type.value,
            ),
        )

    @staticmethod
    def _deduplicate_and_rank(
        evidence: list[PolicyEvidence],
    ) -> list[PolicyEvidence]:
        unique: dict[tuple[str, str], PolicyEvidence] = {}

        for item in evidence:
            normalized_content = " ".join(
                item.content.casefold().split()
            )
            key = (
                item.source.casefold().strip(),
                normalized_content,
            )

            existing = unique.get(key)

            if existing is None:
                unique[key] = item
                continue

            existing_score = (
                existing.relevance_score
                if existing.relevance_score is not None
                else -1.0
            )
            new_score = (
                item.relevance_score
                if item.relevance_score is not None
                else -1.0
            )

            if new_score > existing_score:
                unique[key] = item

        def sort_key(item: PolicyEvidence) -> tuple[float, str, str]:
            score = (
                item.relevance_score
                if item.relevance_score is not None
                else -1.0
            )

            return (
                -score,
                item.policy_type.value,
                item.source,
            )

        return sorted(unique.values(), key=sort_key)
