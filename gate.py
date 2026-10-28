"""Public pre_tool_call line for one Wyoming describe. Speech providers do not call this."""
from __future__ import annotations

import contextvars
import hashlib
import json
import os
import threading
import time
from typing import Any

if __package__:
    from .messages import (
        APPROVAL_TEXT_MAX,
        approval_too_long,
        host_process_blocked,
        not_approved,
        unattended_blocked,
    )
else:
    from messages import (
        APPROVAL_TEXT_MAX,
        approval_too_long,
        host_process_blocked,
        not_approved,
        unattended_blocked,
    )

TOOL = "wyoming_voice_status"
_LOCK = threading.Lock()
_STASH: dict[tuple, tuple[tuple, float]] = {}
_STASH_TTL = 600
# The same platforms Hermes treats as unattended: webhook, msgraph_webhook, api_server.
_UNATTENDED_PLATFORMS = frozenset({"webhook", "msgraph_webhook", "api_server"})
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _context_value(name: str):
    """Value of a ContextVar with this name, if this turn set one.

    An unset var is absent. A non-string sentinel is not a value, so the caller
    falls back to the process environment. An explicit empty string does not.
    """
    try:
        current = contextvars.copy_context()
    except Exception:
        return None
    for var, value in current.items():
        if getattr(var, "name", None) == name:
            return value
    return None


def session_flag(name: str) -> str:
    """ContextVar first, including an explicit empty string. Otherwise the process environment."""
    value = _context_value(name)
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "1" if value else ""
    return str(os.environ.get(name) or "")


def _flag_on(name: str) -> bool:
    return session_flag(name).strip().lower() in _TRUTHY


def unattended_reason() -> str | None:
    """Why this turn cannot ask a person, or None when a person can be asked.

    Hermes reads a stored always before its own cron, -q, and unattended refusals.
    A describe is an outbound connection, so those turns are refused here.
    yolo and approvals off are not in this list.
    """
    if os.environ.get("HERMES_PLUGIN_HOST_PROCESS") == "1":
        return "plugin_host"
    if _flag_on("HERMES_CRON_SESSION"):
        return "a cron job"
    if _flag_on("HERMES_SINGLE_QUERY_SESSION"):
        return "a single-query run (hermes -q)"
    platform = session_flag("HERMES_SESSION_PLATFORM").strip().lower()
    if platform in _UNATTENDED_PLATFORMS:
        return f"an unattended {platform} session"
    return None


def one_call_rule_key(which: str, targets: list[str]) -> str:
    """Hermes stores session and always under this key. The same plan matches; another does not."""
    body = json.dumps({"targets": list(targets), "which": which}, sort_keys=True, separators=(",", ":"))
    return TOOL + ":" + hashlib.sha256(body.encode()).hexdigest()[:16]


def approval_text(targets: list[str]) -> str:
    joined = "; ".join(targets)
    count = len(targets)
    noun = "describe" if count == 1 else "describes"
    return (
        f"Send {count} Wyoming {noun} to {joined}. "
        "No audio and no text to speak are sent. Cleartext TCP, no login."
    )


def _ids(kwargs: dict) -> tuple[str, str]:
    return (str(kwargs.get("session_id") or ""), str(kwargs.get("task_id") or ""))


def _stash_key(payload: dict, ids: tuple[str, str]) -> tuple:
    # The whole call, plus the session and task. One which does not cover another
    # spelling, another session, or another task.
    fields = {str(key): payload[key] for key in payload}
    return (TOOL, json.dumps(fields, sort_keys=True, default=str), ids[0], ids[1])


def remember_describe(payload: dict, ids: tuple[str, str], plan: tuple) -> None:
    with _LOCK:
        _STASH[_stash_key(payload, ids)] = (plan, time.monotonic())


def take_describe(payload: dict, ids: tuple[str, str], plan: tuple) -> str | None:
    """Pop this call's plan. Missing, stale, or different means do not connect."""
    with _LOCK:
        found = _STASH.pop(_stash_key(payload, ids), None)
    if found is None:
        return not_approved()
    stored, made = found
    if time.monotonic() - made > _STASH_TTL:
        return "BLOCKED: the approval is too old. Nothing was sent."
    if stored != plan:
        return "The target changed after the preview. Nothing was sent."
    return None


def _clear(ids: tuple[str, str]) -> None:
    """Drop previews for this session and task. Other rooms stay until they are answered."""
    with _LOCK:
        for key in [k for k in _STASH if k[2:] == ids]:
            del _STASH[key]


def on_pre_tool_call(tool_name: str = "", args: dict | None = None, **kwargs: Any):
    """Approve one describe. Any other tool, including speech, stays silent."""
    if tool_name != TOOL:
        return None
    # Every describe call in this session and task starts clean. A preview kept after a
    # refusal, a block, or a later modify must not authorize a different call.
    # Other rooms keep their own previews while they wait for an answer.
    _clear(_ids(kwargs))
    if __package__:
        from .service import describe_targets, fold_which
    else:
        from service import describe_targets, fold_which
    payload = dict(args) if isinstance(args, dict) else {}
    folded = fold_which(payload)
    if isinstance(folded, dict):
        return None
    targets, error = describe_targets(folded)
    if error or not targets:
        return None
    reason = unattended_reason()
    if reason == "plugin_host":
        return {"action": "block", "message": host_process_blocked()}
    if reason:
        return {"action": "block", "message": unattended_blocked(reason)}
    text = approval_text(targets)
    if len(text) > APPROVAL_TEXT_MAX or "\n" in text or "`" in text:
        return {"action": "block", "message": approval_too_long()}
    remember_describe(payload, _ids(kwargs), tuple(targets))
    return {
        "action": "approve",
        "message": text,
        "rule_key": one_call_rule_key(folded, targets),
    }
