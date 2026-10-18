import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from infrastructure.stacks.data_stack import NovaMartDataStack
from infrastructure.stacks.image_stack import NovaMartImageStack
from infrastructure.stacks.policy_stack import NovaMartPolicyStack
from infrastructure.stacks.runtime_stack import NovaMartRuntimeStack


@pytest.fixture(scope="module")
def runtime_templates():
    app = cdk.App()
    data = NovaMartDataStack(app, "Data")
    policy = NovaMartPolicyStack(app, "Policy", policy_bucket=data.policy_bucket)
    images = NovaMartImageStack(app, "Images")
    runtime = NovaMartRuntimeStack(
        app, "Runtime", image_repository=images.repository,
        workflow_table=data.workflow_table, customer_table=data.customer_table,
        order_table=data.order_table, knowledge_bases=policy.knowledge_bases,
    )
    app.synth()
    return Template.from_stack(runtime).to_json(), Template.from_stack(images).to_json()


def resource(template, resource_type):
    matches = [r for r in template["Resources"].values() if r["Type"] == resource_type]
    assert len(matches) == 1
    return matches[0]


def statements(template):
    return resource(template, "AWS::IAM::Policy")["Properties"]["PolicyDocument"]["Statement"]


def actions(statement):
    value = statement["Action"]
    return {value} if isinstance(value, str) else set(value)


def test_runtime_image_is_required_by_digest_and_registry_is_immutable(runtime_templates):
    template, images = runtime_templates
    digest = template["Parameters"]["RuntimeImageDigest"]
    assert digest["AllowedPattern"] == "sha256:[a-f0-9]{64}"
    assert "Default" not in digest
    runtime = resource(template, "AWS::BedrockAgentCore::Runtime")["Properties"]
    uri = json.dumps(runtime["AgentRuntimeArtifact"]["ContainerConfiguration"]["ContainerUri"])
    assert "RuntimeImageDigest" in uri
    assert "@" in uri
    repo = resource(images, "AWS::ECR::Repository")
    assert repo["Properties"]["ImageTagMutability"] == "IMMUTABLE"
    assert repo["Properties"]["ImageScanningConfiguration"]["ScanOnPush"] is True
    assert repo["DeletionPolicy"] == "Retain"


def test_runtime_has_http_iam_defaults_and_bounded_session_lifecycle(runtime_templates):
    template, _ = runtime_templates
    runtime = resource(template, "AWS::BedrockAgentCore::Runtime")["Properties"]
    assert runtime["ProtocolConfiguration"] == "HTTP"
    assert runtime["NetworkConfiguration"] == {"NetworkMode": "PUBLIC"}
    assert "AuthorizerConfiguration" not in runtime  # Service default: AWS IAM.
    assert runtime["LifecycleConfiguration"] == {
        "IdleRuntimeSessionTimeout": 300, "MaxLifetime": 1800,
    }


def test_runtime_environment_uses_stack_references_without_secrets(runtime_templates):
    template, _ = runtime_templates
    env = resource(template, "AWS::BedrockAgentCore::Runtime")["Properties"]["EnvironmentVariables"]
    for key in (
        "WORKFLOW_TABLE_NAME", "CUSTOMER_TABLE_NAME", "ORDER_TABLE_NAME",
        "RETURNS_KB_ID", "SHIPPING_KB_ID", "WARRANTY_KB_ID",
    ):
        assert "Fn::ImportValue" in env[key]
    assert "AWS_ACCESS_KEY_ID" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env


def test_runtime_can_write_workflows_but_only_read_customer_and_order_data(runtime_templates):
    template, _ = runtime_templates
    found_workflow_write = False
    for statement in statements(template):
        allowed = actions(statement)
        if not any(a.startswith("dynamodb:") for a in allowed):
            continue
        refs = json.dumps(statement["Resource"])
        assert statement["Resource"] != "*"
        assert "dynamodb:DeleteItem" not in allowed
        if "CustomerTable" in refs or "OrderTable" in refs:
            assert allowed <= {"dynamodb:GetItem", "dynamodb:Query"}
        if "dynamodb:PutItem" in allowed:
            assert "WorkflowStateTable" in refs
            found_workflow_write = True
    assert found_workflow_write


def test_retrieval_is_limited_to_the_three_knowledge_bases(runtime_templates):
    template, _ = runtime_templates
    retrieval = [s for s in statements(template) if "bedrock:Retrieve" in actions(s)]
    assert len(retrieval) == 1
    assert len(retrieval[0]["Resource"]) == 3
    for domain in ("Returns", "Shipping", "Warranty"):
        assert domain in json.dumps(retrieval[0]["Resource"])


def test_model_permissions_cover_exact_profiles_and_cross_region_models(runtime_templates):
    template, _ = runtime_templates
    inference = [s for s in statements(template) if "bedrock:InvokeModel" in actions(s)]
    assert len(inference) == 1
    refs = json.dumps(inference[0]["Resource"])
    assert "foundation-model/*" not in refs
    assert "inference-profile/us.anthropic.claude-haiku" in refs
    assert "inference-profile/us.anthropic.claude-sonnet" in refs
    assert "foundation-model/anthropic.claude-haiku" in refs
    assert "foundation-model/anthropic.claude-sonnet" in refs
    assert actions(inference[0]) == {"bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"}


def test_runtime_waits_for_execution_policy_and_has_restricted_trust(runtime_templates):
    template, _ = runtime_templates
    runtime = resource(template, "AWS::BedrockAgentCore::Runtime")
    policy_id = next(k for k, r in template["Resources"].items() if r["Type"] == "AWS::IAM::Policy")
    assert policy_id in runtime["DependsOn"]
    trust = resource(template, "AWS::IAM::Role")["Properties"]["AssumeRolePolicyDocument"]
    assert trust["Statement"][0]["Principal"] == {"Service": "bedrock-agentcore.amazonaws.com"}
    assert trust["Statement"][0]["Condition"]["StringEquals"]["aws:SourceAccount"] == {
        "Ref": "AWS::AccountId",
    }
    log_actions = set()
    for statement in statements(template):
        allowed = actions(statement)
        if not any(a.startswith("logs:") for a in allowed):
            continue
        log_actions.update(allowed)
        refs = json.dumps(statement["Resource"])
        assert statement["Resource"] != "*"
        if allowed != {"logs:DescribeLogGroups"}:
            assert "/aws/bedrock-agentcore/runtimes/novamart_support-*" in refs
    assert {"logs:PutResourcePolicy", "logs:DescribeLogGroups", "logs:PutLogEvents"} <= log_actions
