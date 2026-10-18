"""AWS CDK application for NovaMart."""

import os

import aws_cdk as cdk

from infrastructure.stacks.data_stack import NovaMartDataStack
from infrastructure.stacks.image_stack import NovaMartImageStack
from infrastructure.stacks.policy_stack import NovaMartPolicyStack
from infrastructure.stacks.runtime_stack import NovaMartRuntimeStack

app = cdk.App(outdir=os.environ.get("CDK_OUTDIR", "cdk.out"))

data_stack = NovaMartDataStack(
    app,
    "NovaMartDataStack",
    project_name="novamart-support",
)

policy_stack = NovaMartPolicyStack(
    app,
    "NovaMartPolicyStack",
    policy_bucket=data_stack.policy_bucket,
    project_name="novamart-support",
)

image_stack = NovaMartImageStack(app, "NovaMartImageStack")
NovaMartRuntimeStack(
    app,
    "NovaMartRuntimeStack",
    image_repository=image_stack.repository,
    workflow_table=data_stack.workflow_table,
    customer_table=data_stack.customer_table,
    order_table=data_stack.order_table,
    knowledge_bases=policy_stack.knowledge_bases,
)

app.synth()
