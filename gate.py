"""Approval gate for the describe tool. Speech providers do not call this."""
from __future__ import annotations

import importlib
import os
import uuid
from typing import Any, Callable

if __package__:
    from .messages import (
        APPROVAL_TEXT_MAX,
        approval_too_long,
        host_process_blocked,
        not_approved,
    )
else:
    from messages import (
        APPROVAL_TEXT_MAX,
        approval_too_long,
        host_process_blocked,
        not_approved,
    )

Loader = Callable[[str, str], tuple[str, Any]]


def _load(module: str, name: str) -> tuple[str, Any]:
    try:
        mod = importlib.import_module(module)
    except Exception:
        return "failed", None
    if not hasattr(mod, name):
        return "missing", None
    try:
        return "ok", getattr(mod, name)
    except Exception:
        return "failed", None


_BLOCKS = (
    ("tools.approval_context", "_is_cron_approval_context",
     "BLOCKED: cron cannot describe a Wyoming server. Nothing was sent."),
    ("tools.approval", "_yolo_active",
     "BLOCKED: Hermes yolo is on, so nobody would be asked. Nothing was sent."),
    ("tools.approval_context", "_get_approval_mode",
     "BLOCKED: Hermes approvals are off, so nobody would be asked. Nothing was sent."),
    ("tools.approval_context", "_is_single_query_approval_context",
     "BLOCKED: a single-query session cannot describe a Wyoming server. Nothing was sent."),
    ("tools.approval_context", "_is_unattended_platform_approval_context",
     "BLOCKED: an unattended session cannot describe a Wyoming server. Nothing was sent."),
)


def block_reason(loader: Loader = _load) -> str | None:
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        return host_process_blocked()
    for module, name, message in _BLOCKS:
        status, fn = loader(module, name)
        if status != "ok":
            return f"BLOCKED: could not read Hermes approval state ({name}). Nothing was sent."
        try:
            value = fn()
        except Exception:
            return f"BLOCKED: the Hermes approval check failed ({name}). Nothing was sent."
        if name == "_get_approval_mode":
            if value == "off":
                return message
            if not isinstance(value, str) or not value:
                return "BLOCKED: could not read approvals.mode. Nothing was sent."
            continue
        if value:
            return message
    status, fn = loader("tools.approval", "request_tool_approval")
    if status != "ok" or not callable(fn):
        return "BLOCKED: Hermes approval could not be loaded, so nothing was sent."
    return None


def approval_text(targets: list[str]) -> str:
    joined = "; ".join(targets)
    count = len(targets)
    noun = "describe" if count == 1 else "describes"
    return (
        f"Send {count} Wyoming {noun} to {joined}. "
        "No audio and no text to speak are sent. Cleartext TCP, no login."
    )


def approve_describe(targets: list[str], loader: Loader = _load) -> str | None:
    """Return an error string, or None when a person approved this one call."""
    reason = block_reason(loader)
    if reason:
        return reason
    text = approval_text(targets)
    if len(text) > APPROVAL_TEXT_MAX:
        return approval_too_long()
    _status, fn = loader("tools.approval", "request_tool_approval")
    call_id = uuid.uuid4().hex
    try:
        result = fn(
            "wyoming_voice_status",
            text,
            rule_key=f"wyoming_voice_status:{call_id}",
        )
    except Exception:
        return "BLOCKED: the Hermes approval request failed, so nothing was sent."
    if not isinstance(result, dict) or result.get("approved") is not True:
        return not_approved()
    return None
