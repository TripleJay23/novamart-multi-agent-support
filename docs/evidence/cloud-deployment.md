# Cloud deployment evidence â€” 18 October 2026

This record covers revision `8a95621420a0b5ae4ea9fdff4e52993ad4abc732` and a
subsequent uncommitted Decimal-serialization repair in `us-east-1`, using synthetic
NovaMart data. The accompanying
[machine-readable evidence](cloud-verification.json) preserves source hashes,
ingestion statistics, and real retrieval excerpts. Account numbers, generated
resource identifiers, and credential material are omitted from public evidence.

## Verified foundation

| Check | Observed result |
| --- | --- |
| Data stack | `UPDATE_COMPLETE`; deployment added outputs without replacing tables or the document bucket |
| Image registry | `CREATE_COMPLETE`; immutable tags and scan-on-push configured |
| Policy stack | `CREATE_COMPLETE`; three isolated vector indexes, retrieval roles, Knowledge Bases, and data sources |
| Policy upload | Three versioned S3 objects; SHA-256 hashes recorded |
| Ingestion | Returns, shipping, and warranty each scanned and indexed one document, with zero failures |
| Direct retrieval | Each domain returned a chunk from its expected S3 prefix; returns evidence includes the premium 60-day window |
| Demo seed | Zero records created; two existing customers and four existing orders preserved |

These are actual AWS results. The source policies remain demonstration documents;
shipping and warranty do not establish real commercial coverage or guarantees.
Direct retrieval does not prove that a generated answer uses its evidence correctly.

## Release image

A fresh ARM64 image was built from the clean committed revision and health-checked
locally as non-root user `10001:10001`, without AWS credentials or mounts. ECR
confirmed the pushed tag `8a95621` at:

```text
sha256:a8d521e05243779a40847c5b5f3daf4f0e32319f4636e9471a611e308051e90b
```

The OCI index contains one `linux/arm64` application manifest and one build
attestation. The application manifest digest is:

```text
sha256:6ba82653c544943b9c0aebb1c5859580247bbdad09ebbb443c124ba38c65e171
```

The first push timed out waiting for an ECR response. A retry reused uploaded
layers and completed successfully. The digest above comes from ECR, not solely
from the local Docker image.

The completed scan of the ARM64 application manifest reported **7 HIGH, 4 MEDIUM,
and 2 LOW** findings. Six HIGH findings identify `util-linux` and one identifies
`zlib`. These scanner findings have not been resolved or accepted as production
risk. This image is a development deployment candidate, not a security-cleared
release. Scanning the OCI index itself did not return a scan; the findings belong
to the application manifest.

The original pushed image predates the serialization repair described below. The
corrected working-tree candidate was rebuilt as `novamart-support:decimal-fix`,
passed all [seven container checks](container-decimal-fix-smoke.json), and was
pushed under the separate immutable ECR tag `8a95621-decimal-fix`:

```text
sha256:76e0870b3994590a20179b11c07d68af8bca234d9b313783725dc4454ce91276
```

This is a working-tree candidate, not a clean committed release. Its application
source hash is recorded in the container report. Its own ARM64 manifest scan also
reported **7 HIGH, 4 MEDIUM, and 2 LOW** findings. The earlier image and evidence
remain intact. This candidate contains the Decimal repair only; the subsequent
[communication milestone](communication-grounding.md#current-deployment-candidate)
records the newer deployment candidate with both repairs.

## Live application checks and repair

The application was exercised locally against real Bedrock models, the deployed
Knowledge Bases, and DynamoDB. These checks used the developer's AWS credentials,
not the proposed runtime execution role. They do not establish AgentCore hosting
or that the runtime role can perform the same operations.

The initial policy scenario completed. The refund scenario then failed after
inventory: DynamoDB deserialized nested numeric context values as `Decimal`, and
the next specialist prompt passed them directly to `json.dumps`. The workflow was
marked failed; the failed baseline was retained. Order verification had not run.

The repair uses `WorkflowState.model_dump(mode="json")` for the existing prompt
fields, preserving exact Decimal values as strings without converting money to
binary floats. A regression test resumes a workflow through the real DynamoDB
adapter using Moto and verifies numeric context reaches the refund specialist.
It failed before the repair and passed afterward. The full suite now reports
**184 passed**, with the existing SDK deprecation warning; Ruff and strict mypy
also passed. See the [JUnit report](pytest-decimal-fix.xml) and
[verification transcript](decimal-fix-verification.txt).

All three scenarios then completed with the repaired working tree:

| Scenario | Observed smoke result | Route |
| --- | --- | --- |
| Premium return policy | Response includes the source's 60-day window | Policy â†’ Communication |
| `CUST-1001` / `ORD-1001` refund eligibility | Eligible amount 149.99; no payment executed | Inventory â†’ Refund â†’ Communication |
| `CUST-1001` / `ORD-1002` order status | Response reports shipped | Inventory â†’ Communication |

For each scenario, the final response, route, status, and version matched a fresh
consistent DynamoDB read, and terminal resume returned the unchanged summary.
[Sanitized requests and responses](live-application.json) include observed single-run
durations. These are smoke checks, not latency benchmarks or a formal evaluation.

The generated refund response adds a dollar symbol although the source schema does
not specify currency, and the order response says delivery should occur "soon"
without a delivery estimate. These are unresolved answer-quality observations;
the checks assert the amount/status and workflow behavior, not full factual or
policy compliance of every generated sentence.

## Deployment permissions and failures

The pre-existing CDK execution role lacked ECR creation permission. After explicit
owner approval, a scoped `NovaMartDeploymentResources` inline policy was attached
and read back successfully. Existing managed policies were preserved. The failed
image stack had no physical repository; only that empty stack record was removed
before the successful foundation retry.

The first runtime creation returned CloudFormation `AccessDenied` and rolled back.
IAM simulation showed allowed runtime creation, endpoint creation, runtime tagging,
and role passing, but denied tagging in the workload-identity namespace. A narrow
tagging repair was applied to the same approved NovaMart identity resources, with
zero IAM Access Analyzer validation findings. The fully rolled-back runtime stack
record was removed before retrying. The second attempt was also denied: the tagging
repair did not resolve runtime creation. No hosted invocation was attempted.

CloudTrail event lookup was explicitly denied by the account's organization policy.
No attempt was made to change that organization policy or grant broad administrative
access. Policy validation and simulation are supporting checks, not substitutes for
a successful deployment.

## Runtime acceptance

Runtime creation remains blocked. The registered CloudFormation create handler lists
`iam:CreateServiceLinkedRole` among its required permissions. Simulation initially confirmed that
the deployment role lacked it for the existing AgentCore Runtime Identity service-linked
role. A one-action addition was prepared with its exact role ARN and
`iam:AWSServiceName=runtime-identity.bedrock-agentcore.amazonaws.com`; Access Analyzer
returned zero findings. The owner separately approved this addition; it was applied
and read back successfully before a third deployment attempt. That attempt also
returned `AccessDenied`: neither scoped repair resolved creation. The precise denied
API or condition remains unconfirmed because organization policy blocks CloudTrail
lookup. An account administrator needs to inspect the denied runtime creation event
before another permission change can be justified.

An administrator with permitted CloudTrail access can inspect `CreateAgentRuntime`
events in `us-east-1` around **11:57:45, 12:02:10, and 12:07:25 UTC on 18 October
2026**, filtering for the CDK execution role and runtime name `novamart_support`.
The useful next evidence is the denied action, resource, and condition from those
events, rather than another generic CloudFormation failure message. Keep raw audit
records private and sanitize any excerpt before adding it to this package.

The runtime stack finished in `ROLLBACK_COMPLETE`. Every resource in that failed
stack is `DELETE_COMPLETE`, and a live runtime listing confirms that no
`novamart_support` runtime remains. The data, policy, and image stacks remain deployed.

No hosted model response, persisted hosted workflow, or live resume result is claimed.
Guardrails, customer ownership authorization, full observability, concurrency failure
injection, and formal model evaluation remain separate acceptance work.

## Reproduction and local raw records

The reviewed deployment used Node `24.21.0`, AWS CDK CLI `2.1145.0`, the locked Python
environment, and a saved cloud assembly. The existing runbooks document the
[policy steps](../deployment/policy-environment.md) and
[runtime steps](../deployment/agentcore-runtime.md).

Private raw outputs are retained locally under ignored `cdk.out/release/`, including
deployment diffs and transcripts, the approved IAM policy and readback, build
metadata, ECR push attempts and scan findings, source object versions, ingestion
jobs, retrieval results, and seed output. They contain environment identifiers and
must be reviewed before sharing. The public JSON is a selected, sanitized evidence
record, not a verbatim copy of every AWS response. No cloud screenshots have been
captured for this snapshot.

## Subsequent grounding and image review

The [communication milestone](communication-grounding.md) adds a versioned five-case
live evaluation and a fresh 195-test snapshot. It also records package availability
and a Trixie image experiment that was not adopted. Those records do not change the
three denied runtime attempts or establish hosted acceptance.
