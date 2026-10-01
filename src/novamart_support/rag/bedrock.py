"""Amazon Bedrock Knowledge Base policy retrievers."""

from typing import Any

import boto3
from botocore.exceptions import ClientError

from novamart_support.domain import PolicyEvidence, PolicyType
from novamart_support.exceptions import PolicyRetrievalError


class BedrockKnowledgeBaseRetriever:
    """Retrieve grounded text evidence from one Bedrock Knowledge Base."""

    def __init__(
        self,
        policy_type: PolicyType,
        knowledge_base_id: str,
        *,
        region_name: str = "us-east-1",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        runtime_client: Any | None = None,
    ) -> None:
        cleaned_knowledge_base_id = knowledge_base_id.strip()

        if not cleaned_knowledge_base_id:
            raise ValueError("knowledge_base_id must not be empty.")

        if bool(guardrail_id) != bool(guardrail_version):
            raise ValueError(
                "guardrail_id and guardrail_version must be configured together."
            )

        self._policy_type = policy_type
        self._knowledge_base_id = cleaned_knowledge_base_id
        self._guardrail_id = guardrail_id
        self._guardrail_version = guardrail_version
        self._client = runtime_client or boto3.client(
            "bedrock-agent-runtime",
            region_name=region_name,
        )

    @property
    def policy_type(self) -> PolicyType:
        return self._policy_type

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> list[PolicyEvidence]:
        cleaned_query = query.strip()

        if not cleaned_query:
            raise ValueError("Policy query must not be empty.")

        if limit < 1:
            raise ValueError("limit must be at least 1.")

        request: dict[str, Any] = {
            "knowledgeBaseId": self._knowledge_base_id,
            "retrievalQuery": {
                "text": cleaned_query,
            },
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": limit,
                }
            },
        }

        if self._guardrail_id is not None:
            request["guardrailConfiguration"] = {
                "guardrailId": self._guardrail_id,
                "guardrailVersion": self._guardrail_version,
            }

        try:
            response = self._client.retrieve(**request)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "Unknown")
            message = error.get("Message", str(exc))

            raise PolicyRetrievalError(
                f"Bedrock retrieval failed for {self.policy_type.value}: "
                f"{code}: {message}"
            ) from exc

        if response.get("guardrailAction") == "INTERVENED":
            raise PolicyRetrievalError(
                f"Guardrail intervened during {self.policy_type.value} retrieval."
            )

        evidence: list[PolicyEvidence] = []

        for result in response.get("retrievalResults", []):
            content = result.get("content", {})

            if content.get("type") not in (None, "TEXT"):
                continue

            text = content.get("text")

            if not isinstance(text, str) or not text.strip():
                continue

            raw_score = result.get("score")
            score = (
                float(raw_score)
                if isinstance(raw_score, (int, float))
                else None
            )

            metadata = result.get("metadata")
            normalized_metadata = (
                dict(metadata)
                if isinstance(metadata, dict)
                else {}
            )

            normalized_metadata["knowledge_base_id"] = (
                self._knowledge_base_id
            )

            document_id = result.get("documentId")

            if isinstance(document_id, str) and document_id:
                normalized_metadata["document_id"] = document_id

            evidence.append(
                PolicyEvidence(
                    policy_type=self.policy_type,
                    content=text.strip(),
                    source=self._extract_source(result),
                    relevance_score=score,
                    metadata=normalized_metadata,
                )
            )

        return evidence

    def _extract_source(self, result: dict[str, Any]) -> str:
        location = result.get("location")

        if isinstance(location, dict):
            for location_name in (
                "s3Location",
                "webLocation",
                "confluenceLocation",
                "salesforceLocation",
                "sharePointLocation",
                "oneDriveLocation",
                "googleDriveLocation",
                "kendraDocumentLocation",
                "customDocumentLocation",
                "sqlLocation",
            ):
                details = location.get(location_name)

                if not isinstance(details, dict):
                    continue

                for field_name in ("uri", "url", "id", "query"):
                    value = details.get(field_name)

                    if isinstance(value, str) and value.strip():
                        return value.strip()

        document_id = result.get("documentId")

        if isinstance(document_id, str) and document_id.strip():
            return document_id.strip()

        return f"bedrock-kb:{self._knowledge_base_id}"


class ReturnsPolicyRetriever(BedrockKnowledgeBaseRetriever):
    def __init__(
        self,
        knowledge_base_id: str,
        *,
        region_name: str = "us-east-1",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        runtime_client: Any | None = None,
    ) -> None:
        super().__init__(
            PolicyType.RETURNS,
            knowledge_base_id,
            region_name=region_name,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            runtime_client=runtime_client,
        )


class ShippingPolicyRetriever(BedrockKnowledgeBaseRetriever):
    def __init__(
        self,
        knowledge_base_id: str,
        *,
        region_name: str = "us-east-1",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        runtime_client: Any | None = None,
    ) -> None:
        super().__init__(
            PolicyType.SHIPPING,
            knowledge_base_id,
            region_name=region_name,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            runtime_client=runtime_client,
        )


class WarrantyPolicyRetriever(BedrockKnowledgeBaseRetriever):
    def __init__(
        self,
        knowledge_base_id: str,
        *,
        region_name: str = "us-east-1",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        runtime_client: Any | None = None,
    ) -> None:
        super().__init__(
            PolicyType.WARRANTY,
            knowledge_base_id,
            region_name=region_name,
            guardrail_id=guardrail_id,
            guardrail_version=guardrail_version,
            runtime_client=runtime_client,
        )
