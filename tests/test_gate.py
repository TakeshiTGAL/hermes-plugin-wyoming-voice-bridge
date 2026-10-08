import os

from gate import approval_text, approve_describe, block_reason
from messages import APPROVAL_TEXT_MAX, host_process_blocked


def _loader(table):
    def load(module, name):
        key = (module, name)
        if key not in table:
            return "missing", None
        value = table[key]
        if value == "boom":
            def boom():
                raise RuntimeError("boom")
            return "ok", boom
        if value == "bad":
            return "failed", None
        return "ok", (lambda *args, value=value, **kwargs: value)
    return load


def _clear(monkeypatch):
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    return {
        ("tools.approval_context", "_is_cron_approval_context"): False,
        ("tools.approval", "_yolo_active"): False,
        ("tools.approval_context", "_get_approval_mode"): "manual",
        ("tools.approval_context", "_is_single_query_approval_context"): False,
        ("tools.approval_context", "_is_unattended_platform_approval_context"): False,
        ("tools.approval", "request_tool_approval"): {"approved": True},
    }


def test_each_unattended_context_is_blocked(monkeypatch):
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    blocked = {
        ("tools.approval_context", "_is_cron_approval_context"): True,
        ("tools.approval", "_yolo_active"): True,
        ("tools.approval_context", "_get_approval_mode"): "off",
        ("tools.approval_context", "_is_single_query_approval_context"): True,
        ("tools.approval_context", "_is_unattended_platform_approval_context"): True,
    }
    base = _clear(monkeypatch)
    for key, value in blocked.items():
        table = dict(base)
        table[key] = value
        reason = block_reason(_loader(table))
        assert reason and reason.startswith("BLOCKED:"), key


def test_each_approval_part_fails_closed_three_ways(monkeypatch):
    parts = [
        ("tools.approval_context", "_is_cron_approval_context"),
        ("tools.approval", "_yolo_active"),
        ("tools.approval_context", "_get_approval_mode"),
        ("tools.approval_context", "_is_single_query_approval_context"),
        ("tools.approval_context", "_is_unattended_platform_approval_context"),
        ("tools.approval", "request_tool_approval"),
    ]
    for module, name in parts:
        for kind in ("missing", "bad", "boom"):
            table = _clear(monkeypatch)
            if kind == "missing":
                del table[(module, name)]
            else:
                table[(module, name)] = kind
            if name == "request_tool_approval":
                reason = approve_describe(["127.0.0.1:10300"], _loader(table))
            else:
                reason = block_reason(_loader(table))
            assert reason and reason.startswith("BLOCKED:"), (name, kind, reason)


def test_missing_check_fails_closed(monkeypatch):
    table = _clear(monkeypatch)
    del table[("tools.approval", "_yolo_active")]
    reason = block_reason(_loader(table))
    assert reason.startswith("BLOCKED:")
    assert "Nothing was sent" in reason


def test_host_process_sends_nothing(monkeypatch):
    table = _clear(monkeypatch)
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    reason = block_reason(_loader(table))
    assert reason == host_process_blocked()


def test_approval_uses_a_fresh_rule_key(monkeypatch):
    seen = []

    def request_tool_approval(name, text, *, rule_key=""):
        seen.append((name, text, rule_key))
        return {"approved": True}

    table = _clear(monkeypatch)
    def load(module, name):
        if (module, name) == ("tools.approval", "request_tool_approval"):
            return "ok", request_tool_approval
        return _loader(table)(module, name)

    assert approve_describe(["127.0.0.1:10300"], load) is None
    assert approve_describe(["127.0.0.1:10300"], load) is None
    assert seen[0][2] != seen[1][2]
    assert seen[0][2].startswith("wyoming_voice_status:")
    assert "audio" in seen[0][1].lower()
    assert len(seen[0][1]) <= APPROVAL_TEXT_MAX


def test_denied_approval_does_not_look_approved(monkeypatch):
    table = _clear(monkeypatch)
    table[("tools.approval", "request_tool_approval")] = {"approved": False, "message": ""}
    reason = approve_describe(["127.0.0.1:1"], _loader(table))
    assert "not approved" in reason


def test_overlong_question_is_not_submitted(monkeypatch):
    called = []
    table = _clear(monkeypatch)

    def request_tool_approval(*_a, **_k):
        called.append(1)
        return {"approved": True}

    def load(module, name):
        if (module, name) == ("tools.approval", "request_tool_approval"):
            return "ok", request_tool_approval
        return _loader(table)(module, name)

    huge = "h" * (APPROVAL_TEXT_MAX + 50)
    reason = approve_describe([huge], load)
    assert called == []
    assert "one message" in reason
    one = approval_text(["127.0.0.1:10300"])
    both = approval_text(["127.0.0.1:10300", "10.1.1.8:10200"])
    assert one.startswith("Send 1 Wyoming describe to ")
    assert both.startswith("Send 2 Wyoming describes to ")
    assert "No audio and no text to speak" in both
    assert "10.1.1.8:10200" in both
    assert len(one) <= APPROVAL_TEXT_MAX
    assert len(both) <= APPROVAL_TEXT_MAX
