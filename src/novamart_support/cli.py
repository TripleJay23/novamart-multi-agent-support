"""Command-line entrypoint for NovaMart multi-agent support."""

import argparse
import json
import sys
from collections.abc import Sequence

from novamart_support.config import get_settings
from novamart_support.domain import WorkflowState, WorkflowStatus
from novamart_support.exceptions import NovaMartError
from novamart_support.runtime import build_application


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novamart-support",
        description=(
            "Run or resume NovaMart multi-agent customer-support workflows."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Start and execute a new support workflow.",
    )
    run_parser.add_argument(
        "--session-id",
        required=True,
        help="Unique workflow session identifier.",
    )
    run_parser.add_argument(
        "--query",
        required=True,
        help="Customer support request.",
    )
    run_parser.add_argument(
        "--customer-id",
        help="Known NovaMart customer identifier.",
    )
    run_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit a machine-readable workflow summary.",
    )

    resume_parser = subparsers.add_parser(
        "resume",
        help="Resume an existing persisted workflow.",
    )
    resume_parser.add_argument(
        "--session-id",
        required=True,
        help="Existing workflow session identifier.",
    )
    resume_parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Emit a machine-readable workflow summary.",
    )

    return parser


def _workflow_summary(
    state: WorkflowState,
) -> dict[str, object]:
    """Return a safe CLI-facing workflow summary."""

    return {
        "session_id": state.session_id,
        "customer_id": state.customer_id,
        "request_type": state.request_type.value,
        "status": state.status.value,
        "route_history": list(state.route_history),
        "final_response": state.final_response,
        "version": state.version,
    }


def _emit_result(
    state: WorkflowState,
    *,
    json_output: bool,
) -> int:
    if json_output:
        print(
            json.dumps(
                _workflow_summary(state),
                indent=2,
                sort_keys=True,
            )
        )
    elif state.final_response:
        print(state.final_response)
    else:
        print(
            f"Workflow {state.session_id} finished with "
            f"status={state.status.value}."
        )

    if state.status is WorkflowStatus.FAILED:
        return 2

    return 0


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """Execute the NovaMart command-line interface."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
        application = build_application(settings)

        if args.command == "run":
            state = application.runtime.run(
                args.session_id,
                args.query,
                customer_id=args.customer_id,
            )
        else:
            state = application.runtime.resume(
                args.session_id
            )

        return _emit_result(
            state,
            json_output=args.json_output,
        )

    except (NovaMartError, ValueError) as exc:
        print(
            f"error: {exc}",
            file=sys.stderr,
        )
        return 1
