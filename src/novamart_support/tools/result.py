"""Stable response contract for agent-facing tool handlers."""

from typing import Any, NotRequired, TypedDict


class ToolErrorPayload(TypedDict):
    code: str
    message: str


class ToolResponse(TypedDict):
    ok: bool
    data: NotRequired[Any]
    error: NotRequired[ToolErrorPayload]


def success(data: Any) -> ToolResponse:
    """Return a successful tool response."""

    return {
        "ok": True,
        "data": data,
    }


def failure(code: str, message: str) -> ToolResponse:
    """Return a controlled tool failure."""

    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
