# Communication grounding regression

`communication-v1.json` contains five synthetic, versioned cases derived from two
observed live answers: a refund response invented a currency, and an order response
predicted arrival without a delivery estimate. The repaired CommunicationAgent
must acknowledge missing facts and preserve supplied facts.

| Case | Intended behavior |
| --- | --- |
| Refund without currency | Exact amount, no invented denomination, missing currency stated |
| Refund with currency | Supplied USD denomination retained |
| Shipped order without estimate | Shipped status retained, missing estimate stated, no predicted arrival |
| Shipped order with estimate | Supplied date retained and qualified as an estimate |
| Customer asks for unsupported currency | Requested denomination does not override missing source facts |

The positive controls supply currency and estimate facts directly in fixture context.
They do not add those fields to the application's customer/order schema or prove that
the deployed inventory service supplies them.

## Run

Validate fixture models and regular expressions without AWS calls:

```bash
uv run --locked python tool/evaluate_communication.py --validate-only
```

Run real Bedrock inference using the configured worker model and standard credential
provider. This incurs model usage; it creates no DynamoDB, S3, or AgentCore resources:

```bash
uv run --locked python tool/evaluate_communication.py --live --output cdk.out/communication-eval.json
```

Use `--profile YOUR_PROFILE` to select an existing AWS profile. Credentials are never
included in the report. Each case gets a fresh agent and an in-memory workflow fixture.
The runner records the response, model/region, prompt and dataset hashes, duration,
successful context-tool reads, and whether the fixture changed. It exits nonzero if
any case fails or returns invalid structured output. Interrupted runs retain partial
evidence with `ok: false`.

## What the checks establish

Required patterns stop empty or irrelevant responses from passing. Forbidden patterns
flag the observed currency and delivery language. A successful read of the expected
workflow context is required; the fixture must remain unchanged. The offline tests
exercise bad historical-style answers, good controls, missing tool use, and invalid
regular expressions.

These are lexical checks. They can flag a prohibited word used in a denial and can
miss unsupported claims expressed with other wording. Review every response against
its fixture; a green report does not establish general factual correctness, payment
safety, broad prompt-injection resistance, or production readiness. The recorded run
still has human review pending. One adversarial query is one regression case, not a
security evaluation.

This scope is **CommunicationAgent with live Bedrock and in-memory context**. It does
not exercise routing, DynamoDB persistence, retrieval, AgentCore hosting, or runtime-role
permissions. The earlier full application smoke record covers different boundaries.

## Recorded evidence

On 18 October 2026, all five automated cases passed with the configured Sonnet worker
model. See the [raw selected results](../docs/evidence/communication-eval.json),
[historical answer reassessment](../docs/evidence/communication-baseline.json), and
[195-test verification](../docs/evidence/communication-verification.txt).

The historical answers came from full workflows with different context content. Their
reassessment demonstrates that the new checks catch the recorded defects; it is not a
controlled before/after model comparison. The new prompt and evaluation are uncommitted
changes on base revision `8a95621`.
