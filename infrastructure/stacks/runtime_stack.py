"""IAM-authenticated AgentCore runtime using a prebuilt ARM64 ECR image."""

from aws_cdk import ArnFormat, CfnOutput, CfnParameter, Environment, Stack, Tags
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_bedrockagentcore as agentcore
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from constructs import Construct

from novamart_support.config import DEFAULT_ORCHESTRATOR_MODEL_ID, DEFAULT_WORKER_MODEL_ID


class NovaMartRuntimeStack(Stack):
    """Application role and runtime; deployment requires a built image digest."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        image_repository: ecr.IRepository,
        workflow_table: dynamodb.ITable,
        customer_table: dynamodb.ITable,
        order_table: dynamodb.ITable,
        knowledge_bases: dict[str, bedrock.CfnKnowledgeBase],
        env: Environment | None = None,
    ) -> None:
        super().__init__(scope, construct_id, env=env)

        image_digest = CfnParameter(
            self,
            "RuntimeImageDigest",
            type="String",
            allowed_pattern=r"sha256:[a-f0-9]{64}",
            description="Digest of the verified linux/arm64 image in the NovaMart ECR repository.",
        )
        runtime_name = "novamart_support"
        runtime_arn_pattern = self.format_arn(
            service="bedrock-agentcore",
            resource="runtime",
            resource_name="*",
            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
        )
        self.execution_role = iam.Role(
            self,
            "RuntimeExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {"aws:SourceArn": runtime_arn_pattern},
                },
            ),
        )

        image_repository.grant_pull(self.execution_role)
        for table in (customer_table, order_table):
            self.execution_role.add_to_policy(iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:Query"], resources=[table.table_arn],
            ))
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
            resources=[workflow_table.table_arn],
        ))
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:Retrieve"],
            resources=[kb.attr_knowledge_base_arn for kb in knowledge_bases.values()],
        ))

        model_resources = []
        for model_id in (DEFAULT_ORCHESTRATOR_MODEL_ID, DEFAULT_WORKER_MODEL_ID):
            # Defaults are US cross-region profiles. Authorize each profile and
            # its exact underlying model across possible destination regions.
            model_resources.extend([
                self.format_arn(
                    service="bedrock",
                    resource="inference-profile",
                    resource_name=model_id,
                    arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                ),
                self.format_arn(
                    service="bedrock", region="*", account="",
                    resource="foundation-model", resource_name=model_id.removeprefix("us."),
                    arn_format=ArnFormat.SLASH_RESOURCE_NAME,
                ),
            ])
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            resources=model_resources,
        ))

        log_group_arn = self.format_arn(
            service="logs", resource="log-group",
            resource_name=f"/aws/bedrock-agentcore/runtimes/{runtime_name}-*",
            arn_format=ArnFormat.COLON_RESOURCE_NAME,
        )
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogGroup", "logs:DescribeLogStreams", "logs:PutResourcePolicy"],
            resources=[log_group_arn],
        ))
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:DescribeLogGroups"],
            resources=[self.format_arn(
                service="logs", resource="log-group", resource_name="*",
                arn_format=ArnFormat.COLON_RESOURCE_NAME,
            )],
        ))
        self.execution_role.add_to_policy(iam.PolicyStatement(
            actions=["logs:CreateLogStream", "logs:PutLogEvents"],
            resources=[f"{log_group_arn}:log-stream:*"],
        ))

        self.runtime = agentcore.CfnRuntime(
            self,
            "SupportRuntime",
            agent_runtime_name=runtime_name,
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=agentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=image_repository.repository_uri_for_digest(
                        image_digest.value_as_string,
                    ),
                ),
            ),
            role_arn=self.execution_role.role_arn,
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            protocol_configuration="HTTP",
            lifecycle_configuration=agentcore.CfnRuntime.LifecycleConfigurationProperty(
                idle_runtime_session_timeout=300,
                max_lifetime=1800,
            ),
            environment_variables={
                "AWS_REGION": self.region,
                "PROJECT_NAME": "novamart-support",
                "WORKFLOW_TABLE_NAME": workflow_table.table_name,
                "CUSTOMER_TABLE_NAME": customer_table.table_name,
                "ORDER_TABLE_NAME": order_table.table_name,
                "RETURNS_KB_ID": knowledge_bases["returns"].attr_knowledge_base_id,
                "SHIPPING_KB_ID": knowledge_bases["shipping"].attr_knowledge_base_id,
                "WARRANTY_KB_ID": knowledge_bases["warranty"].attr_knowledge_base_id,
                "ORCHESTRATOR_MODEL_ID": DEFAULT_ORCHESTRATOR_MODEL_ID,
                "WORKER_MODEL_ID": DEFAULT_WORKER_MODEL_ID,
            },
        )
        # The runtime must not start until attached execution permissions exist.
        self.runtime.node.add_dependency(self.execution_role)
        CfnOutput(self, "RuntimeArn", value=self.runtime.attr_agent_runtime_arn)
        CfnOutput(self, "ExecutionRoleArn", value=self.execution_role.role_arn)
        Tags.of(self).add("Project", "novamart-support")
        Tags.of(self).add("ManagedBy", "AWS-CDK")
