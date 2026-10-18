# Communication grounding evidence â€” 18 October 2026

This working-tree milestone builds on `8a95621` and the Decimal serialization
repair. It addresses two observed answer defects: labeling an unspecified amount
with a currency symbol, and predicting delivery from a shipped status alone.

The CommunicationAgent now explicitly separates amounts from currencies, shipped
status from delivery estimates, and customer requests from authoritative facts.
Missing values must be acknowledged; recorded estimates remain estimates.

## Verification

| Check | Result | Evidence and boundary |
| --- | --- | --- |
| Full local suite | 195 passed; one existing SDK warning | [JUnit](pytest-communication.xml), including 11 new evaluation-check tests |
| Ruff / strict mypy | Passed; 45 application source files checked by mypy | [Transcript](communication-verification.txt); evaluator code is linted but outside the application mypy target |
| Fixture validation | Five cases and regular expressions validated | [Versioned dataset](../../evals/communication-v1.json) |
| Live CommunicationAgent cases | Five automated passes | [Recorded answers](communication-eval.json), using real Bedrock inference and in-memory workflow context |
| Context use / mutation | Expected context was read; all fixtures unchanged | Per-case checks in the live report |
| Historical defect detection | Both recorded bad answers fail the new checks | [Reassessment](communication-baseline.json); different context scope, not a controlled A/B comparison |

The cases cover missing currency, supplied currency, missing delivery estimate,
supplied estimate, and a customer asking for an unsupported denomination. Prompt
and dataset hashes, model ID, region, and single-run durations are recorded. No
credential values, account IDs, or deployed resource identifiers are required.

The full suite consists of 161 unit, 14 mocked integration, and 20 infrastructure
tests. Its results are separate from the five model evaluations; they must not be
added together as if they were the same test layer.

## Limits and remaining findings

The checks are lexical. They require expected content, reject specified unsupported
language, and verify context-tool use. They do not establish all-sentence grounding,
broad prompt-injection resistance, payment safety, or end-to-end support quality.
One adversarial case is not a security certification. Human review is pending.

The adversarial-case response still promises confirmation after future processing,
which is not established by the fixture. That wording is outside these narrow checks
and remains a quality issue. This record preserves the generated answer rather than
editing it into an expected result.

The earlier [live application record](live-application.json) exercised routing and
DynamoDB under the previous communication prompt. The new evaluation exercises only
CommunicationAgent, its real context tool, and Bedrock. It does not refresh those
full-workflow results, prove runtime-role permissions, or establish AgentCore hosting.
See the [evaluation guide](../../evals/README.md) for reproduction commands and scoring
limits.

## Current deployment candidate

The grounding repair was rebuilt on the unchanged Bookworm base and passed all
[seven container checks](container-communication-smoke.json). Its installed application
source hash matches the working tree. The temporary container was removed. The image
was pushed under the new immutable tag `8a95621-communication-v1` at:

```text
sha256:39ef89bf8e37b3ba1f29344f02cb5ce856319ae714645baa44422354565ba461
```

[Image provenance and scan results](communication-image.json) record the ECR-confirmed
index and ARM64 application digests. Its own completed scan reports **7 HIGH, 4 MEDIUM,
and 2 LOW** findings. It is an uncommitted development candidate, not a security-cleared
or hosted release. The local container checks use no credentials or model calls; the
five live model cases ran on the development host, not inside this image.

## Image review and deployment blocker

A fresh package-index check inside an isolated Bookworm candidate reported no
available upgrades for `util-linux` or `zlib1g`, and a simulated system upgrade changed
zero packages. See the [captured package review](os-package-review.txt).

Debian's trackers list the installed Bookworm versions as vulnerable for
[CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) and
[CVE-2026-85091](https://security-tracker.debian.org/tracker/CVE-2026-85091).
The supported Trixie release fixes
[CVE-2026-53613](https://security-tracker.debian.org/tracker/CVE-2026-53613) and
[CVE-2026-53615](https://security-tracker.debian.org/tracker/CVE-2026-53615), while
other findings remain. The separately built Trixie candidate passed all seven
[container checks](container-trixie-experiment.json), and its ECR scan reported
3 HIGH, 9 MEDIUM, and 3 LOW findings versus the earlier Bookworm candidate's
7 HIGH, 4 MEDIUM, and 2 LOW. See the [full selected comparison](image-review.json).

Trixie introduced two HIGH glibc findings (`CVE-2026-5435`, `CVE-2026-19499`),
and the Debian tracker still lists four util-linux findings as vulnerable on Trixie
even though that ECR scan does not report them. A lower scanner count does not
establish that all previous vulnerabilities are resolved. The base migration was
not adopted: the repository Dockerfile remains on Bookworm. Neither image is
security-cleared, and no finding has been waived.

Runtime creation remains blocked: the failed stack is `ROLLBACK_COMPLETE`, and a
fresh [CloudTrail request](cloudtrail-access.json) is still explicitly denied by
organization policy. The owner's console screenshots also show the `LookupEvents`
deny; an empty Event history under that denial does not prove that no events exist.
The screenshots are not included in public evidence because they contain environment
identifiers. This confirms the diagnostic-access blocker, not the underlying cause
of runtime creation failure. No new
deployment attempt or IAM permission change was made during this milestone. A
read-only simulation also found caller-side ECR reads denied; that is an unconfirmed
candidate dependency, not an established cause. The runtime execution policy already
defines image-pull access. The administrator audit-event request in the
[deployment evidence](cloud-deployment.md) remains the next diagnostic step.
