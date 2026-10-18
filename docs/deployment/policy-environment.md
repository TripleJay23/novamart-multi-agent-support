# Deploy the NovaMart policy environment

This runbook prepares the existing data stack and three Bedrock Knowledge Bases.
It does not deploy AgentCore or apply guardrails to model calls. The infrastructure
has local synthesis and assertion coverage; live creation, ingestion, and retrieval
must be recorded separately before claiming cloud acceptance.

## Resources and boundaries

`NovaMartDataStack` owns the three DynamoDB tables and private S3 document bucket.
`NovaMartPolicyStack` references that bucket and defines:

- One encrypted S3 vector bucket with three separate indexes.
- Returns, shipping, and warranty Knowledge Bases using Titan Text Embeddings V2
  at 1,024 dimensions with cosine distance.
- Three S3 data sources, each restricted to its own `policies/<domain>/` prefix.
- One service role per domain with access to that domain's S3 objects and vector
  index, plus invocation permission for the embedding model.
- Output IDs for application configuration and ingestion commands.

Trust is restricted to Bedrock Knowledge Bases in this account and region. The
trust condition uses `knowledge-base/*` because IDs are assigned during creation;
object access and vector access remain scoped to each domain. The service roles
are ingestion/retrieval roles, not the future application runtime role.

Source uploads and ingestion are explicit steps. Redeploying a stack does not
automatically upload policies or refresh embeddings.

The [policy documents](../../data/policies/) are versioned **demonstration content**.
Returns mirror the deterministic eligibility rules. Shipping and warranty sources
explicitly describe missing commercial terms, so a grounded answer should acknowledge
those limits. Replace these documents with owner-approved policies for a real retailer.

## Prerequisites and local verification

Use Python 3.12, uv, the Node version declared in `.node-version`, AWS CLI v2, and a
compatible AWS CDK CLI. Select the AWS account/profile you intend to use and region
`us-east-1`. Check that Bedrock Knowledge Bases, S3 Vectors, and the embedding model
are supported in your chosen region, and that the deployer has the required IAM and
CloudFormation permissions. The application also needs separate model inference and
retrieval permissions; this stack does not grant permissions to your CLI identity.

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest tests/infrastructure -q
uv run --locked --extra dev python -m infrastructure.app
```

Synthesis creates local `cdk.out` artifacts and makes no deployment. Review the generated
templates, IAM statements, retention behavior, and costs before deploying.

## Deploy resources

Using your selected AWS profile and region:

```bash
aws sts get-caller-identity
cdk bootstrap
cdk diff NovaMartDataStack NovaMartPolicyStack
cdk deploy NovaMartDataStack NovaMartPolicyStack
aws cloudformation describe-stacks --stack-name NovaMartDataStack --query 'Stacks[0].Outputs'
aws cloudformation describe-stacks --stack-name NovaMartPolicyStack --query 'Stacks[0].Outputs'
```

The stack names and project prefix default to `NovaMartDataStack`, `NovaMartPolicyStack`,
and `novamart-support`. Both stacks deploy in the same account/region. Do not point the
application at resources from another environment.

## Upload versioned source documents

Replace `YOUR_POLICY_BUCKET` with the data stack's `PolicyBucketName` output. Run from
the repository root; these commands upload only the three policy directories and do
not delete other objects in the bucket.

```bash
aws s3 sync data/policies/returns s3://YOUR_POLICY_BUCKET/policies/returns/
aws s3 sync data/policies/shipping s3://YOUR_POLICY_BUCKET/policies/shipping/
aws s3 sync data/policies/warranty s3://YOUR_POLICY_BUCKET/policies/warranty/
```

The source bucket is versioned. Record the Git revision, policy version, object key,
and S3 version ID when capturing release evidence. `sync` does not remove old policy
filenames; when replacing a policy version, ensure the included prefix does not contain
contradictory active documents before the next ingestion.

## Start and verify ingestion

Use each domain's `KnowledgeBaseId` and `DataSourceId` outputs in the corresponding
command. Placeholder IDs below must be replaced with actual stack outputs.

```bash
aws bedrock-agent start-ingestion-job --knowledge-base-id RETURNS_KB_ID --data-source-id RETURNS_DATA_SOURCE_ID
aws bedrock-agent start-ingestion-job --knowledge-base-id SHIPPING_KB_ID --data-source-id SHIPPING_DATA_SOURCE_ID
aws bedrock-agent start-ingestion-job --knowledge-base-id WARRANTY_KB_ID --data-source-id WARRANTY_DATA_SOURCE_ID
```

Save each returned ingestion job ID. Poll each job with the matching domain's IDs:

```bash
aws bedrock-agent get-ingestion-job --knowledge-base-id YOUR_KB_ID --data-source-id YOUR_DATA_SOURCE_ID --ingestion-job-id YOUR_JOB_ID
```

Wait for `COMPLETE`, inspect document statistics, and require no failed documents.
An accepted `start-ingestion-job` request is not proof of completed ingestion. On
failure, inspect `failureReasons`, permissions, source prefixes, and model availability.
Do not publish a successful retrieval claim from a failed or empty ingestion.

## Configure the application and check retrieval

Set `RETURNS_KB_ID`, `SHIPPING_KB_ID`, and `WARRANTY_KB_ID` in the ignored `.env` file
using the outputs for this environment. All three are required by application composition.
Preserve the existing credentials provider chain; do not put AWS keys in the file.

First check source retrieval directly, substituting a Knowledge Base ID:

```bash
aws bedrock-agent-runtime retrieve --knowledge-base-id YOUR_RETURNS_KB_ID --retrieval-query '{"text":"What is the premium return window?"}'
```

The evidence should contain the premium 60-day return window and a source location
under `policies/returns/`. Repeat for shipping and warranty with domain-appropriate
questions and record the source metadata, not only the generated answer.

Then seed synthetic customer/order data and invoke a new workflow:

```bash
uv run --locked novamart-seed --json
uv run --locked novamart-support run --session-id policy-smoke-001 --query "What is the premium return window?" --json
```

Use a new session ID for each run. Model IDs and inference permissions must also be
valid for the selected AWS account. Capture the workflow JSON, source evidence,
ingestion statistics, and sanitized screenshots in the [evidence package](../evidence/README.md).

## Retention and cleanup

The policy vector bucket and indexes use `RETAIN`, and data sources retain embeddings
when removed. Destroying the policy stack leaves those retained storage resources and
their ongoing charges for deliberate cleanup. Empty/delete retained indexes and the
vector bucket only after verifying they contain no needed data; retain an inventory of
their physical identifiers before deleting the stack. A later redeploy does not
automatically adopt resources retained from an earlier stack.

The existing data stack still uses `DESTROY` for its tables and document bucket.
The non-empty versioned document bucket can block deletion; there is no automatic
object deletion in this project. Review and apply a production retention policy before
storing real data. Remove the policy stack before the data stack because it imports the
document-bucket reference. No teardown command is run by the application or this guide.

## AWS references

- [Knowledge Base vector-store prerequisites](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-setup.html)
  for matching dimensions and Bedrock metadata keys.
- [Knowledge Base service-role permissions](https://docs.aws.amazon.com/bedrock/latest/userguide/kb-permissions.html)
  for source, model, vector-index, and trust boundaries.
- [S3 Vectors index CloudFormation reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-s3vectors-index.html)
  for vector-index properties and deployment permissions.
- [StartIngestionJob CLI reference](https://docs.aws.amazon.com/cli/latest/reference/bedrock-agent/start-ingestion-job.html)
  for starting document synchronization.
