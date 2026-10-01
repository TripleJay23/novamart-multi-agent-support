"""Persistent data resources for NovaMart."""

from aws_cdk import (
    CfnOutput,
    Environment,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_s3 as s3
from constructs import Construct


class NovaMartDataStack(Stack):
    """DynamoDB persistence and policy-document storage."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        project_name: str = "novamart-support",
        env: Environment | None = None,
    ) -> None:
        super().__init__(
            scope,
            construct_id,
            env=env,
        )

        self.workflow_table = dynamodb.Table(
            self,
            "WorkflowStateTable",
            table_name=f"{project_name}-workflow-state",
            partition_key=dynamodb.Attribute(
                name="session_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=(
                dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True,
                )
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.customer_table = dynamodb.Table(
            self,
            "CustomerTable",
            table_name=f"{project_name}-customers",
            partition_key=dynamodb.Attribute(
                name="customer_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=(
                dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True,
                )
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.order_table = dynamodb.Table(
            self,
            "OrderTable",
            table_name=f"{project_name}-orders",
            partition_key=dynamodb.Attribute(
                name="customer_id",
                type=dynamodb.AttributeType.STRING,
            ),
            sort_key=dynamodb.Attribute(
                name="order_id",
                type=dynamodb.AttributeType.STRING,
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=(
                dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True,
                )
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.policy_bucket = s3.Bucket(
            self,
            "PolicyDocumentsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        Tags.of(self).add(
            "Project",
            project_name,
        )
        Tags.of(self).add(
            "ManagedBy",
            "AWS-CDK",
        )

        CfnOutput(
            self,
            "WorkflowTableName",
            value=self.workflow_table.table_name,
        )
        CfnOutput(
            self,
            "CustomerTableName",
            value=self.customer_table.table_name,
        )
        CfnOutput(
            self,
            "OrderTableName",
            value=self.order_table.table_name,
        )
        CfnOutput(
            self,
            "PolicyBucketName",
            value=self.policy_bucket.bucket_name,
        )
