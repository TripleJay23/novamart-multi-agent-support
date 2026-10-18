# NovaMart evidence index

This directory records local verification separately from the cloud evidence still
needed for release. All current records use synthetic data.

## Local verification snapshot

- **Date:** 18 October 2026, Africa/Dar_es_Salaam.
- **Code base revision:** `f8616b520aa3ef4e18beec018c20200a5b916c87`, plus the
  uncommitted policy-infrastructure and AgentCore runtime milestones in the working tree.
- **Environment:** Windows, Python 3.12.13, uv 0.11.14, Node.js v26.7.0.
  Node differs from the repository's `.node-version`; infrastructure assertions passed
  in the recorded environment, which is not evidence of testing the declared version.
- **Changes included:** documentation and local demo; policy infrastructure and synthetic
  policy documents; AgentCore entrypoint and shared CLI summary; default model constants;
  image/runtime infrastructure and packaging; unit/infrastructure assertions and runbooks.
- **Execution:** existing `.venv` interpreter with `PYTHONPATH=src`. The sandbox denied
  reads of installed dependencies; checks were rerun successfully with approved access.

| Artifact | What it proves | Limit |
| --- | --- | --- |
| [pytest-results.xml](pytest-results.xml) | 183 passing test cases: 150 unit, 13 mocked integration, 20 infrastructure | Uses fake models, SDK stubs, Moto, and local CDK assertions; no live inference or deployment |
| [verification.txt](verification.txt) | Captured test summary, Ruff result, mypy result, both CLI help outputs, and synthesis outcome | A dated local snapshot, not a CI or release badge |
| [local_demo.py](local_demo.py) | Reproducible refund decisions and route definitions from real domain services | In-memory data with a fixed clock; not a full agent workflow |
| [local-demo.txt](local-demo.txt) | Captured stdout of the local demo | Eligibility decisions do not execute refunds |
| [container-build.txt](container-build.txt) | Successful locked dependency and package installation into an ARM64 image | Local build only; no ECR push |
| [container-build-metadata.json](container-build-metadata.json) | Resolved base-image digests and resulting local OCI image digest | Build host is amd64; target image is ARM64 |
| [container-smoke.json](container-smoke.json) | Seven successful container checks, source hash, image identity, and cleanup result | No AWS resources, model calls, or credentials |
| [container-runtime.txt](container-runtime.txt) | Logs from the actual container HTTP invocations | SDK completion logs reflect handler execution, not business success |

The XML is the pytest-generated report. The transcript preserves the observed output
with the machine-specific report path shortened to a repository-relative path.
The badge in the root README describes this snapshot and does not update automatically.

## Reproduce local evidence

From the repository root:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest -q --junitxml=docs/evidence/pytest-results.xml
uv run --locked --extra dev ruff check .
uv run --locked --extra dev mypy src/novamart_support
uv run --locked --extra dev python -m novamart_support --help
uv run --locked --extra dev python -m novamart_support.seed --help
uv run --locked --extra dev python docs/evidence/local_demo.py
uv run --locked --extra dev python -m infrastructure.app
```

Record the revision, date, interpreter and Node versions, command exit codes, and full
output when refreshing evidence. Preserve failures instead of replacing them with expected
results. Update the README's counts and dates when publishing a new snapshot.

## Coverage pointers

| Behavior | Tests |
| --- | --- |
| Deterministic specialist sequences and legal transitions | [Workflow service](../../tests/unit/test_workflow_service.py) |
| Typed agent execution, resume, wrong output, and failed workflow state | [Multi-agent runtime](../../tests/unit/test_multi_agent_runtime.py) |
| Version increments, duplicate creation, and stale-write rejection | [DynamoDB workflow repository](../../tests/integration/test_dynamodb_workflow_repository.py) |
| Policy concurrency, deduplication, partial failure, and no-evidence failure | [Policy service](../../tests/unit/test_policy_service.py) |
| Bedrock retrieval request/response and guardrail handling | [Retriever adapter](../../tests/unit/test_bedrock_policy_retriever.py) |
| Return windows, delivery checks, and refund amounts | [Refund service](../../tests/unit/test_refund_service.py) |
| Repeatable sample data and non-overwriting seed behavior | [Seed integration](../../tests/integration/test_seed_data.py) |
| Table keys, billing configuration, and bucket controls | [CDK data stack](../../tests/infrastructure/test_data_stack.py) |
| KB domain isolation, embedding dimensions, scoped IAM, metadata, encryption, and retention | [CDK policy stack](../../tests/infrastructure/test_policy_stack.py) |
| CLI summaries, run/resume, and error output | [CLI](../../tests/unit/test_cli.py) |
| SDK HTTP endpoints, strict payloads, context sessions, fresh agents, and safe errors | [AgentCore entrypoint](../../tests/unit/test_agentcore_entrypoint.py) |
| Immutable images, digest selection, role scope, environment references, and lifecycle | [Runtime and image stacks](../../tests/infrastructure/test_runtime_stack.py) |

The SDK HTTP test emits one `datetime.utcnow()` deprecation warning from installed
`bedrock-agentcore` 0.1.7. The warning was not suppressed. Container build and local smoke
checks subsequently passed; no ECR push or AgentCore deployment was performed.

## Container verification

On 18 October 2026, Docker Desktop 4.94.0 / Engine 29.8.2 built and ran
`novamart-support:local-arm64` using the `desktop-linux` builder. The engine is amd64;
the target image is `linux/arm64`, and execution uses Docker's ARM64 emulation. The
container reports `aarch64`, Python 3.12.15, and effective UID 10001.

Seven checks passed: no credentials/mounts and non-root execution; installed application
source matches the working tree; healthy `/ping`; missing session rejected; missing
query rejected; payload session override rejected; and a valid request without cloud
configuration returns `configuration_error`. The temporary container was removed.

The source hash in the report covers package Python files. Documentation was updated
after the build; the image's bundled README and wheel metadata reflect the build-time
documentation. The application source remains identical. Build provenance records the
base Git revision, but includes uncommitted working-tree content; it is not a clean release.

Reproduce from the repository root after installing Docker:

```bash
docker buildx build --platform linux/arm64 --load --progress plain --iidfile docs/evidence/container-image-id.txt --metadata-file docs/evidence/container-build-metadata.json -t novamart-support:local-arm64 .
uv run --locked python tool/verify_container.py --image novamart-support:local-arm64
```

The captured build transcript retains PowerShell's `NativeCommandError` formatting
around Docker's normal progress on stderr. The actual build exit code was 0, the image
loaded successfully, and its digest matches the smoke report. This formatting is not a
build failure. Both the transcript and generated report are preserved as UTF-8 text;
transcript line endings and trailing whitespace were normalized for Git.

The local OCI image digest is not evidence that an image has been pushed to ECR. Record
the digest returned by ECR for the selected release image before runtime deployment.

## Cloud evidence to capture

No items in this table have been captured for NovaMart in this package. These are
acceptance targets, not claims of implemented or passing cloud behavior.

| Capture | Required supporting record | What a reviewer should verify |
| --- | --- | --- |
| AgentCore runtime and invocation | Deployed revision, deployment command, runtime configuration, sanitized request/response | The deployed entrypoint executes this application |
| Refund conversation and workflow record | Synthetic customer/order, seed reference, CLI JSON, persisted context | Inventory → Refund → Communication; eligibility and amount agree with source facts |
| Order-status and account flows | CLI session, route history, matching order/customer records | Only the necessary specialists run; facts match stored records |
| Policy answer and retrieval sources | Query, document version, retrieved evidence, source metadata, final response | Claims are supported by the ingested returns/shipping/warranty policies |
| Guardrail intervention and clean control | Guardrail version, adversarial input, clean input, assessments, invocation trace | Protection is applied at the intended boundary and legitimate support still succeeds |
| Partial retrieval failure | Induced failure, surviving evidence, final response, logs | Degraded retrieval is reported without unsupported policy claims |
| Workflow conflict and resume | Competing versions, rejected write, interrupted active workflow, subsequent route history | Concurrency protection and persisted continuation work in AWS |
| Request trace and redacted logs | Session correlation, stage timings, error trace, log policy | Operators can diagnose a failed request without exposing customer data |
| End-to-end evaluation | Versioned dataset, runner, raw results, judge/metric configuration | Reported quality, latency, and cost claims match reproducible measurements |

Use genuine console or terminal captures of NovaMart. Include a caption with date,
revision, scenario, and the artifact that supports the image. Sanitize customer details,
credentials, and account-specific identifiers before committing. Do not reuse screenshots
or scores from the separate Bedrock customer-support chatbot as NovaMart evidence.
