import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infrastructure.stacks.data_stack import NovaMartDataStack
from infrastructure.stacks.policy_stack import NovaMartPolicyStack


@pytest.fixture(scope="module")
def policy_template() -> dict:
    app = cdk.App()
    data = NovaMartDataStack(app, "TestData")
    policy = NovaMartPolicyStack(
        app,
        "TestPolicies",
        policy_bucket=data.policy_bucket,
    )
    app.synth()
    return Template.from_stack(policy).to_json()


def resources(template: dict, resource_type: str) -> list[dict]:
    return [r for r in template["Resources"].values() if r["Type"] == resource_type]


def test_each_domain_has_its_own_knowledge_base_source_and_role(policy_template: dict) -> None:
    for resource_type in (
        "AWS::Bedrock::KnowledgeBase",
        "AWS::Bedrock::DataSource",
        "AWS::S3Vectors::Index",
        "AWS::IAM::Role",
    ):
        assert len(resources(policy_template, resource_type)) == 3


def test_vector_dimensions_match_embedding_model_configuration(policy_template: dict) -> None:
    for index in resources(policy_template, "AWS::S3Vectors::Index"):
        props = index["Properties"]
        assert props["DataType"] == "float32"
        assert props["Dimension"] == 1024
        assert props["DistanceMetric"] == "cosine"
        assert props["MetadataConfiguration"]["NonFilterableMetadataKeys"] == [
            "AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA",
        ]

    for kb in resources(policy_template, "AWS::Bedrock::KnowledgeBase"):
        config = kb["Properties"]["KnowledgeBaseConfiguration"]
        assert config["Type"] == "VECTOR"
        vector_config = config["VectorKnowledgeBaseConfiguration"]
        assert "amazon.titan-embed-text-v2:0" in json.dumps(vector_config["EmbeddingModelArn"])
        assert vector_config["EmbeddingModelConfiguration"][
            "BedrockEmbeddingModelConfiguration"
        ]["Dimensions"] == 1024


def test_knowledge_bases_reference_distinct_vector_indexes(policy_template: dict) -> None:
    index_ids = set()
    for kb in resources(policy_template, "AWS::Bedrock::KnowledgeBase"):
        storage = kb["Properties"]["StorageConfiguration"]
        assert storage["Type"] == "S3_VECTORS"
        index_ids.add(storage["S3VectorsConfiguration"]["IndexArn"]["Fn::GetAtt"][0])
    assert len(index_ids) == 3
    for index_id in index_ids:
        assert policy_template["Resources"][index_id]["Type"] == "AWS::S3Vectors::Index"


def test_sources_read_only_their_domain_prefix(policy_template: dict) -> None:
    prefixes = set()
    kb_ids = set()
    for source in resources(policy_template, "AWS::Bedrock::DataSource"):
        props = source["Properties"]
        config = props["DataSourceConfiguration"]
        assert config["Type"] == "S3"
        prefixes.update(config["S3Configuration"]["InclusionPrefixes"])
        kb_ids.add(json.dumps(props["KnowledgeBaseId"]))
        assert props["DataDeletionPolicy"] == "RETAIN"
    assert prefixes == {"policies/returns/", "policies/shipping/", "policies/warranty/"}
    assert len(kb_ids) == 3


def test_role_access_is_scoped_to_one_domain_and_one_index(policy_template: dict) -> None:
    object_resources = set()
    vector_resources = set()
    for role in resources(policy_template, "AWS::IAM::Role"):
        statements = role["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
        for statement in statements:
            assert statement["Resource"] != "*"
            actions = statement["Action"]
            actions = [actions] if isinstance(actions, str) else actions
            if "s3:GetObject" in actions:
                object_resources.add(json.dumps(statement["Resource"]))
            if "s3vectors:PutVectors" in actions:
                assert set(actions) == {
                    "s3vectors:PutVectors", "s3vectors:GetVectors", "s3vectors:DeleteVectors",
                    "s3vectors:QueryVectors", "s3vectors:GetIndex",
                }
                vector_resources.add(json.dumps(statement["Resource"]))
    assert len(object_resources) == 3
    for domain in ("returns", "shipping", "warranty"):
        assert sum(f"policies/{domain}/*" in item for item in object_resources) == 1
    assert len(vector_resources) == 3


def test_role_trust_is_limited_to_bedrock_in_same_account_and_region(policy_template: dict) -> None:
    for role in resources(policy_template, "AWS::IAM::Role"):
        trust = role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
        assert trust["Principal"] == {"Service": "bedrock.amazonaws.com"}
        assert trust["Condition"]["StringEquals"]["aws:SourceAccount"] == {"Ref": "AWS::AccountId"}
        source = json.dumps(trust["Condition"]["ArnLike"]["aws:SourceArn"])
        assert "AWS::Region" in source
        assert "knowledge-base/*" in source


def test_vectors_are_encrypted_and_retained(policy_template: dict) -> None:
    buckets = resources(policy_template, "AWS::S3Vectors::VectorBucket")
    assert len(buckets) == 1
    assert buckets[0]["Properties"]["EncryptionConfiguration"] == {"SseType": "AES256"}
    for resource in buckets + resources(policy_template, "AWS::S3Vectors::Index"):
        assert resource["DeletionPolicy"] == "Retain"
        assert resource["UpdateReplacePolicy"] == "Retain"


def test_outputs_cover_runtime_ids_and_ingestion_sources(policy_template: dict) -> None:
    outputs = policy_template["Outputs"]
    for domain in ("Returns", "Shipping", "Warranty"):
        assert f"{domain}KnowledgeBaseId" in outputs
        assert f"{domain}DataSourceId" in outputs
    assert "VectorBucketArn" in outputs
