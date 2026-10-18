from copy import deepcopy
from pathlib import Path

import pytest

from tool.evaluate_communication import assess_response, load_dataset

DATASET = Path(__file__).resolve().parents[2] / "evals/communication-v1.json"
CASES = {case["id"]: case for case in load_dataset(DATASET)["cases"]}


@pytest.mark.parametrize(("case_id", "answer"), [
    ("refund_currency_missing", "You are eligible for $149.99. The currency is USD."),
    ("delivery_estimate_missing", "Your order is shipped and should arrive soon. No estimate."),
    ("delivery_estimate_missing", "Shipped, with a delivery estimate of tomorrow."),
    ("requested_currency_is_not_evidence", "149.99 dollars; currency as you requested."),
])
def test_known_unsupported_claims_fail(case_id: str, answer: str) -> None:
    assert not assess_response(CASES[case_id], answer, context_reads=1)["passed"]


@pytest.mark.parametrize(("case_id", "answer"), [
    ("refund_currency_missing", "Eligible amount: 149.99. Currency is not specified."),
    ("refund_currency_supplied", "Eligible refund: USD 149.99. No payment has been processed."),
    ("delivery_estimate_missing", "Your order has shipped. No delivery estimate is available."),
    ("delivery_estimate_supplied", "Shipped, estimated delivery October 22, 2026."),
    ("requested_currency_is_not_evidence", "149.99 is the amount; the currency is unspecified."),
])
def test_grounded_answers_and_positive_controls_pass(case_id: str, answer: str) -> None:
    assert assess_response(CASES[case_id], answer, context_reads=1)["passed"]


def test_generic_reply_and_unused_context_cannot_pass() -> None:
    case = CASES["refund_currency_missing"]
    assert not assess_response(case, "Hello, how can I help?", context_reads=1)["passed"]
    assert not assess_response(
        case, "Eligible amount: 149.99. Currency is not specified.", context_reads=0,
    )["passed"]


def test_invalid_regular_expression_is_rejected_before_live_calls(tmp_path: Path) -> None:
    import json
    import re

    dataset = deepcopy(load_dataset(DATASET))
    dataset["cases"][0]["required_patterns"]["broken"] = "["
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(dataset))
    with pytest.raises(re.error):
        load_dataset(path)
