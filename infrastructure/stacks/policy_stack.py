"""Reproducible Bedrock policy retrieval resources backed by S3 Vectors."""

from aws_cdk import ArnFormat, CfnOutput, Environment, RemovalPolicy, Stack, Tags
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

POLICY_DOMAINS = ("returns", "shipping", "warranty")
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


class NovaMartPolicyStack(Stack):
    """One isolated index, retrieval role, KB, and S3 source per policy domain.

    Deployment creates resources only. Documents must be uploaded and ingestion
    explicitly started as described in docs/deployment/policy-environment.md.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        policy_bucket: s3.IBucket,
        project_name: str = "novamart-support",
        env: Environment | None = None,
    ) -> None:
        super().__init__(scope, construct_id, env=env)

        self.vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "PolicyVectors",
            encryption_configuration=s3vectors.CfnVectorBucket.EncryptionConfigurationProperty(
                sse_type="AES256",
            ),
        )
        self.vector_bucket.apply_removal_policy(RemovalPolicy.RETAIN)

        embedding_model_arn = self.format_arn(
            service="bedrock",
            account="",
            resource="foundation-model",
            resource_name=EMBEDDING_MODEL_ID,
            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
        )
        source_arn = self.format_arn(
            service="bedrock",
            resource="knowledge-base",
            resource_name="*",
            arn_format=ArnFormat.SLASH_RESOURCE_NAME,
        )

        self.knowledge_bases: dict[str, bedrock.CfnKnowledgeBase] = {}
        self.data_sources: dict[str, bedrock.CfnDataSource] = {}

        for domain in POLICY_DOMAINS:
            label = domain.title()
            prefix = f"policies/{domain}/"
            index = s3vectors.CfnIndex(
                self,
                f"{label}Index",
                vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
                index_name=f"{domain}-policies",
                data_type="float32",
                dimension=EMBEDDING_DIMENSIONS,
                distance_metric="cosine",
                metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                    non_filterable_metadata_keys=[
                        "AMAZON_BEDROCK_TEXT",
                        "AMAZON_BEDROCK_METADATA",
                    ],
                ),
            )
            index.apply_removal_policy(RemovalPolicy.RETAIN)

            role = iam.Role(
                self,
                f"{label}RetrievalRole",
                assumed_by=iam.ServicePrincipal(
                    "bedrock.amazonaws.com",
                    conditions={
                        "StringEquals": {"aws:SourceAccount": self.account},
                        "ArnLike": {"aws:SourceArn": source_arn},
                    },
                ),
                inline_policies={
                    "PolicyRetrieval": iam.PolicyDocument(
                        statements=[
                            iam.PolicyStatement(
                                actions=["bedrock:InvokeModel"],
                                resources=[embedding_model_arn],
                            ),
                            iam.PolicyStatement(
                                actions=["s3:ListBucket"],
                                resources=[policy_bucket.bucket_arn],
                            ),
                            iam.PolicyStatement(
                                actions=["s3:GetObject"],
                                resources=[policy_bucket.arn_for_objects(f"{prefix}*")],
                            ),
                            iam.PolicyStatement(
                                actions=[
                                    "s3vectors:PutVectors",
                                    "s3vectors:GetVectors",
                                    "s3vectors:DeleteVectors",
                                    "s3vectors:QueryVectors",
                                    "s3vectors:GetIndex",
                                ],
                                resources=[index.attr_index_arn],
                            ),
                        ],
                    ),
                },
            )

            knowledge_base = bedrock.CfnKnowledgeBase(
                self,
                f"{label}KnowledgeBase",
                name=f"{project_name}-{domain}",
                description=f"NovaMart {domain} policy evidence.",
                role_arn=role.role_arn,
                knowledge_base_configuration=(
                    bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                        type="VECTOR",
                        vector_knowledge_base_configuration=(
                            bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                                embedding_model_arn=embedding_model_arn,
                                embedding_model_configuration=(
                                    bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                                        bedrock_embedding_model_configuration=(
                                            bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                                                dimensions=EMBEDDING_DIMENSIONS,
                                            )
                                        ),
                                    )
                                ),
                            )
                        ),
                    )
                ),
                storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                    type="S3_VECTORS",
                    s3_vectors_configuration=(
                        bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                            index_arn=index.attr_index_arn,
                            vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
                        )
                    ),
                ),
            )

            data_source = bedrock.CfnDataSource(
                self,
                f"{label}DataSource",
                name=f"{project_name}-{domain}-documents",
                knowledge_base_id=knowledge_base.attr_knowledge_base_id,
                data_deletion_policy="RETAIN",
                data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                    type="S3",
                    s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                        bucket_arn=policy_bucket.bucket_arn,
                        inclusion_prefixes=[prefix],
                    ),
                ),
                vector_ingestion_configuration=(
                    bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                        chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                            chunking_strategy="FIXED_SIZE",
                            fixed_size_chunking_configuration=(
                                bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                                    max_tokens=300,
                                    overlap_percentage=10,
                                )
                            ),
                        ),
                    )
                ),
            )

            self.knowledge_bases[domain] = knowledge_base
            self.data_sources[domain] = data_source
            CfnOutput(self, f"{label}KnowledgeBaseId", value=knowledge_base.attr_knowledge_base_id)
            CfnOutput(self, f"{label}DataSourceId", value=data_source.attr_data_source_id)

        CfnOutput(self, "VectorBucketArn", value=self.vector_bucket.attr_vector_bucket_arn)
        Tags.of(self).add("Project", project_name)
        Tags.of(self).add("ManagedBy", "AWS-CDK")
