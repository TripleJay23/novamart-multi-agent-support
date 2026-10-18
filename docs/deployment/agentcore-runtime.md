# Host NovaMart on AgentCore Runtime

The runtime entrypoint and CDK definitions are implemented and locally tested. The ARM64
image build and local container smoke checks passed on 18 October 2026; see the
[container evidence](../evidence/README.md#container-verification). A clean-revision
release image has since been pushed to ECR. Runtime creation was denied and hosted
inference remains unverified; see the [cloud evidence](../evidence/cloud-deployment.md)
for permission diagnostics and unresolved image-scan findings.

## Runtime contract

`python -m novamart_support.agentcore` serves the AgentCore SDK's `/ping` and
`/invocations` endpoints on port 8080. Health checks do not construct agents or call AWS.
Each invocation creates fresh Strands agents; conversation history is not cached in a
process-global application container. Workflow progress remains in DynamoDB.

The workflow key comes from **`context.session_id`**, which the SDK obtains from the
AgentCore runtime session header. It must be 33-256 non-whitespace characters. The JSON
payload cannot override the session ID or include unknown fields.

New request:

```json
{"action": "run", "query": "What is the premium return window?"}
```

Customer-specific request:

```json
{"action": "run", "query": "Can I return ORD-1001?", "customer_id": "CUST-1001"}
```

Continuation, using the **same runtime session ID**:

```json
{"action": "resume"}
```

`run` is the default action and requires a non-empty query of at most 10,000 characters.
`resume` must omit query and customer fields. A session represents one persisted support
workflow, not an open-ended chat. A new question needs a new runtime session ID.
Resuming an active workflow executes its next legal step. Resuming a completed or failed
terminal workflow returns its existing state; it does not restart or retry it.

Responses use `{"ok": true, "workflow": {...}}` with the same developer-facing summary
as the local CLI. Internal specialist contexts are excluded. A returned failed workflow
has `ok: false`; validation and execution errors instead have an `error` object with a
stable code and generic message. Raw exception strings and tracebacks are not returned.
Callers must inspect `ok`; HTTP 200 alone is not business success.

This is a **trusted, IAM-authenticated developer/service interface**. IAM permission
to invoke the runtime does not establish that the caller owns a supplied customer ID or
workflow session. Customer authentication and ownership authorization remain necessary
before exposing it to untrusted end users. No customer UI or JWT authorizer is included.

## Local server check

After installing dependencies:

```bash
uv run --locked --extra dev pytest tests/unit/test_agentcore_entrypoint.py -q
uv run --locked python -m novamart_support.agentcore
```

In another terminal:

```bash
curl http://localhost:8080/ping
```

The unit suite exercises both endpoints through the installed SDK with fake application
dependencies. A real invocation of the local server still needs valid AWS configuration,
credentials, model access, tables, and ingested policies. The local HTTP server does not
add IAM authentication; keep local development access restricted to your own environment.

## Build and deploy order

The CDK app defines four stacks:

1. `NovaMartDataStack`: tables and policy documents bucket.
2. `NovaMartPolicyStack`: KBs, vector indexes, and ingestion roles.
3. `NovaMartImageStack`: a retained ECR repository with immutable tags and image scanning.
4. `NovaMartRuntimeStack`: application execution role and IAM-authenticated HTTP runtime.

The image registry deploys separately so the image can be pushed **before** creating the
runtime. The runtime requires an image digest parameter; it has no placeholder image or
mutable-tag default. Do not deploy all stacks until an image is available.

Complete the [policy environment](policy-environment.md) first. Then install and start a
Docker engine with Buildx and ARM64 build support on the build machine. Recorded evidence
uses Docker Desktop 4.94.0 / Engine 29.8.2 with ARM64 emulation on an amd64 engine.

### 1. Create the registry

With the intended AWS account, profile, and region selected:

```bash
cdk diff NovaMartImageStack
cdk deploy NovaMartImageStack
aws cloudformation describe-stacks --stack-name NovaMartImageStack --query 'Stacks[0].Outputs'
```

Use the returned `RepositoryUri` and `RepositoryName` in the following steps. Avoid
reusing a tag: the repository enforces immutable tags.

### 2. Build and inspect the ARM64 container

From the repository root, replacing `YOUR_REPOSITORY_URI` with the output:

```bash
docker buildx build --platform linux/arm64 --load -t YOUR_REPOSITORY_URI:YOUR_RELEASE_TAG .
docker image inspect YOUR_REPOSITORY_URI:YOUR_RELEASE_TAG --format '{{.Os}}/{{.Architecture}}'
docker run --rm --platform linux/arm64 -p 127.0.0.1:8080:8080 YOUR_REPOSITORY_URI:YOUR_RELEASE_TAG
```

Require the image inspection to return `linux/arm64`. While the container is running,
check `http://localhost:8080/ping` in a separate terminal, then stop the local container.
The health endpoint does not need AWS credentials. An actual container invocation needs
an appropriate temporary credential provider and environment configuration; credentials
are not embedded in the image.

The Dockerfile installs locked production dependencies and runs as user 10001. The build
context allowlist includes only source, package metadata, the lockfile, and README; it
excludes `.env`, credentials, tests, evidence, and the host virtual environment. The
runtime starts the installed interpreter directly and does not install dependencies
on startup. Base images remain version-tagged; record their resolved digests in release
evidence if exact rebuild provenance is required.

For repeatable local smoke evidence after building an image:

```bash
uv run --locked python tool/verify_container.py --image YOUR_REPOSITORY_URI:YOUR_RELEASE_TAG
```

The script checks image architecture, non-root execution, installed-source correspondence,
health, malformed requests, and the controlled missing-configuration response. It uses a
temporary localhost-only container without AWS credentials or mounts, saves its report and
logs under `docs/evidence/`, and removes the container afterward. This verifies the unconfigured
image contract; it does not prove a cloud-backed support workflow.

### 3. Push and obtain the digest

Replace `YOUR_REGISTRY_HOST` with the registry portion of the repository URI, such as
`ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com`. Use the same selected AWS account and region:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin YOUR_REGISTRY_HOST
docker push YOUR_REPOSITORY_URI:YOUR_RELEASE_TAG
aws ecr describe-images --repository-name YOUR_REPOSITORY_NAME --image-ids imageTag=YOUR_RELEASE_TAG --query 'imageDetails[0].imageDigest' --output text
```

Review image scan results and save the returned `sha256:` digest, Git revision, build
output, and health-check result. These are release evidence, not just configuration.

### 4. Deploy the runtime

Substitute the real digest, including the `sha256:` prefix and its 64 hexadecimal digits:

```bash
cdk diff NovaMartRuntimeStack --change-set=false
cdk deploy NovaMartRuntimeStack --parameters NovaMartRuntimeStack:RuntimeImageDigest=sha256:YOUR_64_HEX_DIGITS
aws cloudformation describe-stacks --stack-name NovaMartRuntimeStack --query 'Stacks[0].Outputs'
```

The runtime uses the stack-owned repository URI at that digest. Table names and KB IDs
come from CloudFormation references, not a deployed `.env` file. The runtime name is
`novamart_support`; idle session timeout is 300 seconds and maximum lifetime is 1,800 seconds.
Runtime session expiry does not erase the persisted workflow record.

The execution role grants read access to customer/order tables, workflow reads/writes,
retrieval from exactly three KBs, image pulls from the repository, runtime log writes,
and inference on the two configured model profiles and their exact underlying models.
Cross-region foundation-model ARNs use a region wildcard for profile routing, not a
wildcard model ID. ECR authorization uses `Resource: *`, as required by that API.
Role trust is limited to AgentCore runtimes in this account and region.

Runtime creation waits for its attached execution policy. The default inbound authorizer
is AWS IAM; `PUBLIC` network mode does not mean anonymous invocation. Callers need a
separate `bedrock-agentcore:InvokeAgentRuntime` permission for the runtime. No public
resource policy or invoke grant is added by this stack. Full tracing, alarms, model
guardrails, customer authorization, and production network controls remain later gates.

Changing model IDs also requires updating the corresponding IAM resources. The runtime
stack currently derives both from the two default IDs in application configuration.

### 5. Invoke and resume

Replace `YOUR_RUNTIME_ARN` with the `RuntimeArn` output. The example session ID below is
for one workflow; generate a new UUID for each independent question. The committed JSON
examples contain only synthetic support requests.

```bash
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn YOUR_RUNTIME_ARN --runtime-session-id 00000000-0000-4000-8000-000000000001 --content-type application/json --accept application/json --payload fileb://examples/agentcore/run.json response.json
aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn YOUR_RUNTIME_ARN --runtime-session-id 00000000-0000-4000-8000-000000000001 --content-type application/json --accept application/json --payload fileb://examples/agentcore/resume.json response.json
```

Inspect `response.json` after each call before overwriting it with another result. For
release evidence, use distinct sanitized output filenames. If needed, set the ignored
`.env` variable `AGENTCORE_RUNTIME_ARN` to the returned ARN for reference; the existing
`novamart-support` CLI still executes locally and does not read that setting to invoke
the hosted service.

Require `ok: true`, the expected route, a grounded answer, and a matching persisted
workflow record. Verify invalid payloads and missing sessions produce controlled errors.
Capture the [cloud evidence](../evidence/README.md#cloud-evidence-to-capture) before marking
AgentCore deployment accepted.

## Diagnose a denied runtime creation

For a generic CloudFormation `AccessDenied`, inspect the underlying CloudTrail
management event using an identity permitted by the account's organization policy:

1. Open the [CloudTrail console](https://console.aws.amazon.com/cloudtrail/) in
   **US East (N. Virginia), `us-east-1`** and choose **Event history**.
2. Clear the existing lookup filter if necessary. Select **Event name**, enter the
   exact value `CreateAgentRuntime`, and apply the filter.
3. Choose an **Absolute range**. For the recorded failed attempts, select 18 October
   2026, **11:55–12:10 UTC**. In Dar es Salaam this is **14:55–15:10**. The console
   defaults to UTC; check its selected time zone before entering a range.
4. Open the events near **11:57:45, 12:02:10, and 12:07:25 UTC**, then view
   **Event record**. Confirm `requestParameters.agentRuntimeName` is
   `novamart_support` when that field is available.
5. Inspect `errorCode` and `errorMessage`. Keep the exact denied action, resource
   type, and condition, while redacting account IDs, session details, and ARNs in
   shared excerpts. If runtime creation has no error, inspect related failed
   events in the same interval before changing permissions.

If Event history itself returns access denied, an authorized administrator must
perform the lookup. An organization-level explicit deny cannot be repaired by
adding an allow policy to the current role. The recorded operator profile is
subject to such a deny. Do not create a new trail merely to search these recent
management events. See [AWS's Event history instructions](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events-console.html).

## Cleanup and rollback

To roll back application code, redeploy the runtime with a previously verified image
digest. Do not reuse a digest if the expected image has been removed from ECR.
Runtime removal does not delete its table records. Remove the runtime stack before its
image, policy, or data stacks because it imports references from them. ECR is retained
on stack deletion; inventory and deliberately clean up retained images/resources when
they are no longer needed. Existing data and vector retention caveats remain in the
policy runbook. This documentation does not run deployment or cleanup commands.

## References

- [AgentCore container contract and ARM64 deployment](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)
- [AgentCore runtime sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-sessions.html)
- [AgentCore execution-role permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)
- [uv in Docker](https://docs.astral.sh/uv/guides/integration/docker/)
