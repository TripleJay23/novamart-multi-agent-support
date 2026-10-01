import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from infrastructure.stacks.data_stack import NovaMartDataStack


def build_template() -> Template:
    app = cdk.App()

    stack = NovaMartDataStack(
        app,
        "TestNovaMartDataStack",
        project_name="novamart-test",
    )

    return Template.from_stack(stack)


def test_creates_three_dynamodb_tables() -> None:
    template = build_template()

    template.resource_count_is(
        "AWS::DynamoDB::Table",
        3,
    )


def test_workflow_table_uses_session_id_partition_key() -> None:
    template = build_template()

    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "novamart-test-workflow-state",
            "KeySchema": [
                {
                    "AttributeName": "session_id",
                    "KeyType": "HASH",
                }
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_customer_table_uses_customer_id_partition_key() -> None:
    template = build_template()

    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "novamart-test-customers",
            "KeySchema": [
                {
                    "AttributeName": "customer_id",
                    "KeyType": "HASH",
                }
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_order_table_matches_repository_key_contract() -> None:
    template = build_template()

    template.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "novamart-test-orders",
            "KeySchema": [
                {
                    "AttributeName": "customer_id",
                    "KeyType": "HASH",
                },
                {
                    "AttributeName": "order_id",
                    "KeyType": "RANGE",
                },
            ],
            "BillingMode": "PAY_PER_REQUEST",
        },
    )


def test_policy_bucket_is_private_encrypted_and_versioned() -> None:
    template = build_template()

    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {
                        "ServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256",
                        }
                    }
                ]
            },
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
            "VersioningConfiguration": {
                "Status": "Enabled",
            },
        },
    )

    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Action": "s3:*",
                            }
                        )
                    ]
                )
            }
        },
    )
