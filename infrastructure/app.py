"""AWS CDK application for NovaMart."""

import aws_cdk as cdk

from infrastructure.stacks.data_stack import NovaMartDataStack

app = cdk.App()

NovaMartDataStack(
    app,
    "NovaMartDataStack",
    project_name="novamart-support",
)

app.synth()
