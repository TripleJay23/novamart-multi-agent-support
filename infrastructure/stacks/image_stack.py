"""Container registry, deployed before building the AgentCore runtime image."""

from aws_cdk import CfnOutput, Environment, RemovalPolicy, Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class NovaMartImageStack(Stack):
    """An immutable-tag ECR repository retained for deployment traceability."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        env: Environment | None = None,
    ) -> None:
        super().__init__(scope, construct_id, env=env)
        self.repository = ecr.Repository(
            self,
            "RuntimeImages",
            image_scan_on_push=True,
            image_tag_mutability=ecr.TagMutability.IMMUTABLE,
            removal_policy=RemovalPolicy.RETAIN,
        )
        CfnOutput(self, "RepositoryUri", value=self.repository.repository_uri)
        CfnOutput(self, "RepositoryName", value=self.repository.repository_name)
