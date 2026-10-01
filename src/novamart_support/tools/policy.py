"""Agent-facing policy retrieval tool handlers."""

from novamart_support.exceptions import PolicyRetrievalError
from novamart_support.services import PolicyService
from novamart_support.tools.result import ToolResponse, failure, success


class PolicyToolHandlers:
    """Expose grounded policy retrieval to an agent layer."""

    def __init__(self, service: PolicyService) -> None:
        self._service = service

    def search_policies(
        self,
        query: str,
        *,
        limit_per_source: int = 3,
    ) -> ToolResponse:
        try:
            result = self._service.search_all(
                query,
                limit_per_source=limit_per_source,
            )
        except ValueError as exc:
            return failure("invalid_input", str(exc))
        except PolicyRetrievalError as exc:
            return failure("policy_retrieval_failed", str(exc))

        return success(
            {
                "query": result.query,
                "evidence": [
                    item.model_dump(mode="json")
                    for item in result.evidence
                ],
                "failures": [
                    item.model_dump(mode="json")
                    for item in result.failures
                ],
                "is_partial": result.is_partial,
            }
        )
