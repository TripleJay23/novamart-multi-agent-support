from typing import Any

import pytest
from botocore.exceptions import ClientError

from novamart_support.domain import PolicyType
from novamart_support.exceptions import PolicyRetrievalError
from novamart_support.rag import (
    ReturnsPolicyRetriever,
    ShippingPolicyRetriever,
    WarrantyPolicyRetriever,
)


class FakeRuntimeClient:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.requests.append(kwargs)
        return self.response


class FailingRuntimeClient:
    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        raise ClientError(
            {
                "Error": {
                    "Code": "AccessDeniedException",
                    "Message": "not authorized",
                }
            },
            "Retrieve",
        )


def test_returns_retriever_maps_text_result() -> None:
    client = FakeRuntimeClient(
        {
            "guardrailAction": "NONE",
            "retrievalResults": [
                {
                    "content": {
                        "type": "TEXT",
                        "text": "Returns are permitted within the policy window.",
                    },
                    "documentId": "returns-doc-1",
                    "location": {
                        "s3Location": {
                            "uri": "s3://novamart-policies/returns.md",
                        },
                        "type": "S3",
                    },
                    "metadata": {
                        "section": "returns",
                    },
                    "score": 0.93,
                }
            ],
        }
    )

    retriever = ReturnsPolicyRetriever(
        "RETURNSKB1",
        runtime_client=client,
    )

    results = retriever.retrieve(
        "What is the return window?",
        limit=5,
    )

    assert len(results) == 1

    result = results[0]

    assert result.policy_type is PolicyType.RETURNS
    assert result.relevance_score == 0.93
    assert result.source == "s3://novamart-policies/returns.md"
    assert result.metadata["knowledge_base_id"] == "RETURNSKB1"
    assert result.metadata["document_id"] == "returns-doc-1"

    assert client.requests == [
        {
            "knowledgeBaseId": "RETURNSKB1",
            "retrievalQuery": {
                "text": "What is the return window?",
            },
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": 5,
                }
            },
        }
    ]


def test_specialized_retrievers_expose_correct_domain() -> None:
    client = FakeRuntimeClient({"retrievalResults": []})

    returns = ReturnsPolicyRetriever(
        "RETURNSKB1",
        runtime_client=client,
    )
    shipping = ShippingPolicyRetriever(
        "SHIPPINGKB1",
        runtime_client=client,
    )
    warranty = WarrantyPolicyRetriever(
        "WARRANTYKB1",
        runtime_client=client,
    )

    assert returns.policy_type is PolicyType.RETURNS
    assert shipping.policy_type is PolicyType.SHIPPING
    assert warranty.policy_type is PolicyType.WARRANTY


def test_guardrail_configuration_is_forwarded() -> None:
    client = FakeRuntimeClient({"retrievalResults": []})

    retriever = WarrantyPolicyRetriever(
        "WARRANTYKB1",
        guardrail_id="guardrail-123",
        guardrail_version="4",
        runtime_client=client,
    )

    retriever.retrieve("warranty coverage")

    assert client.requests[0]["guardrailConfiguration"] == {
        "guardrailId": "guardrail-123",
        "guardrailVersion": "4",
    }


def test_guardrail_configuration_must_be_complete() -> None:
    client = FakeRuntimeClient({"retrievalResults": []})

    with pytest.raises(ValueError):
        ReturnsPolicyRetriever(
            "RETURNSKB1",
            guardrail_id="guardrail-123",
            runtime_client=client,
        )


def test_guardrail_intervention_raises_controlled_error() -> None:
    client = FakeRuntimeClient(
        {
            "guardrailAction": "INTERVENED",
            "retrievalResults": [],
        }
    )

    retriever = ShippingPolicyRetriever(
        "SHIPPINGKB1",
        runtime_client=client,
    )

    with pytest.raises(PolicyRetrievalError):
        retriever.retrieve("shipping policy")


def test_aws_client_error_is_wrapped() -> None:
    retriever = ReturnsPolicyRetriever(
        "RETURNSKB1",
        runtime_client=FailingRuntimeClient(),
    )

    with pytest.raises(
        PolicyRetrievalError,
        match="AccessDeniedException",
    ):
        retriever.retrieve("returns")


def test_non_text_results_are_ignored() -> None:
    client = FakeRuntimeClient(
        {
            "retrievalResults": [
                {
                    "content": {
                        "type": "IMAGE",
                        "byteContent": "data:image/jpeg;base64,abc",
                    },
                    "score": 0.8,
                },
                {
                    "content": {
                        "type": "TEXT",
                        "text": "   ",
                    },
                    "score": 0.7,
                },
            ]
        }
    )

    retriever = ReturnsPolicyRetriever(
        "RETURNSKB1",
        runtime_client=client,
    )

    assert retriever.retrieve("returns") == []


def test_document_id_is_used_when_location_is_absent() -> None:
    client = FakeRuntimeClient(
        {
            "retrievalResults": [
                {
                    "content": {
                        "type": "TEXT",
                        "text": "Warranty lasts one year.",
                    },
                    "documentId": "warranty-doc-7",
                    "score": 1.2,
                }
            ]
        }
    )

    retriever = WarrantyPolicyRetriever(
        "WARRANTYKB1",
        runtime_client=client,
    )

    result = retriever.retrieve("warranty")[0]

    assert result.source == "warranty-doc-7"
    assert result.relevance_score == 1.2


def test_empty_query_and_invalid_limit_are_rejected() -> None:
    client = FakeRuntimeClient({"retrievalResults": []})

    retriever = ReturnsPolicyRetriever(
        "RETURNSKB1",
        runtime_client=client,
    )

    with pytest.raises(ValueError):
        retriever.retrieve("   ")

    with pytest.raises(ValueError):
        retriever.retrieve("returns", limit=0)


def test_empty_knowledge_base_id_is_rejected() -> None:
    client = FakeRuntimeClient({"retrievalResults": []})

    with pytest.raises(ValueError):
        ReturnsPolicyRetriever(
            "   ",
            runtime_client=client,
        )
