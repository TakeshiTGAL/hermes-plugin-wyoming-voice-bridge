"""Describe approval goes through Hermes's real pre_tool_call hook. No socket."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import gate
from messages import APPROVAL_TEXT_MAX, approval_too_long, host_process_blocked
from service import status

ROOT = Path(__file__).resolve().parents[1]
HERMES_SRC = Path(os.environ.get("HERMES_SRC") or ROOT.parent / "hermes-agent-ref")


def _env(monkeypatch) -> None:
    monkeypatch.setenv("WYOMING_STT_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    monkeypatch.setenv("WYOMING_TTS_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_TTS_PORT", "10200")


def _long_host(fill: str) -> str:
    return ".".join((fill * 63, "b" * 63, "c" * 63, "d" * 61))


@pytest.fixture
def hermes(tmp_path, monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("HERMES_INTERACTIVE", raising=False)
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    monkeypatch.delenv("HERMES_EXEC_ASK", raising=False)
    monkeypatch.delenv("HERMES_YOLO", raising=False)
    monkeypatch.delenv("HERMES_PLUGIN_HOST_PROCESS", raising=False)
    if not (HERMES_SRC / "hermes_cli" / "plugins.py").is_file():
        pytest.skip("set HERMES_SRC to a Hermes source tree")
    src = str(HERMES_SRC)
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        import hermes_cli.plugins as hp
    except Exception as exc:
        pytest.skip("Hermes source needs a newer Python: " + str(exc))
    mgr = hp.PluginManager(scope_key=str(tmp_path))
    mgr._discovered = True
    mgr._hooks["pre_tool_call"] = [gate.on_pre_tool_call]
    monkeypatch.setattr(hp, "get_plugin_manager", lambda: mgr)
    monkeypatch.setattr(hp, "_plugin_manager", mgr)
    # The library check runs as shipped. The installed wyoming tree must be the one
    # this build's sha256 table lists, or the hook returns nothing and these tests fail.
    import importlib.util

    if importlib.util.find_spec("wyoming") is None:
        pytest.skip("wyoming==1.5.4 is not installed in this Python")
    gate._STASH.clear()
    from tools.approval import clear_session
    from tools.approval_context import get_current_session_key

    clear_session(get_current_session_key())
    yield hp
    gate._STASH.clear()
    clear_session(get_current_session_key())


def _assert_blocked_skips_handler(monkeypatch, tool_name, args):
    import agent.tool_executor as executor
    import model_tools

    called = []
    monkeypatch.setattr(model_tools, "_execute_tool", lambda *_a, **_k: called.append("handler") or "{}")
    blocked = model_tools.handle_function_call(tool_name, args, session_id="s1", task_id="t1")
    assert called == []
    assert "BLOCKED" in str(blocked)

    ref = executor._ToolCallRef(tool_name, dict(args), "t1", "c1", [])
    state = executor._ManagedToolResult(
        result=None, args=dict(args), middleware_trace=[], blocked=False, dispatched=False,
    )

    class _Agent:
        session_id = "s1"

    executor._dispatch_authorized_once(
        _Agent(),
        state,
        ref,
        execute=lambda next_args: called.append(next_args) or "ran",
        scope_block=None,
        display_index=None,
        begin_execution=None,
        authorization_gate=None,
    )
    assert called == []
    assert state.blocked is True


def test_other_room_preview_stays(hermes):
    assert gate.on_pre_tool_call(
        "wyoming_voice_status", {"which": "stt"}, session_id="room-a", task_id="t1",
    )["action"] == "approve"
    assert any(key[2:] == ("room-a", "t1") for key in gate._STASH)
    assert gate.on_pre_tool_call(
        "wyoming_voice_status", {"which": "tts"}, session_id="room-b", task_id="t2",
    )["action"] == "approve"
    assert any(key[2:] == ("room-a", "t1") for key in gate._STASH)
    assert any(key[2:] == ("room-b", "t2") for key in gate._STASH)


def test_dispatcher_refusal_does_not_call_the_handler(hermes, monkeypatch):
    _assert_blocked_skips_handler(monkeypatch, "wyoming_voice_status", {"which": "stt"})


def _boom():
    def describe(*_args, **_kwargs):
        raise AssertionError("describe")

    return describe


def test_an_empty_table_asks_nothing_and_the_shipped_table_asks(hermes, monkeypatch):
    import wyoming_pin

    monkeypatch.setattr(wyoming_pin, "WYOMING_SHA256", frozenset())
    silent = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert silent.action is None
    monkeypatch.setattr(wyoming_pin, "WYOMING_SHA256", wyoming_pin.SHIPPED_WYOMING_SHA256)
    asked = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert asked.action == "approve"
    assert "127.0.0.1:10300" in asked.message


def test_write_returns_approve(hermes):
    details = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert details.action == "approve"
    assert details.message
    assert "\n" not in details.message
    assert "`" not in details.message
    assert "127.0.0.1:10300" in details.message
    assert "No audio and no text to speak" in details.message
    assert details.message.startswith("Send 1 Wyoming describe to ")
    both = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "both"})
    assert both.action == "approve"
    assert both.message.startswith("Send 2 Wyoming describes to ")
    assert "127.0.0.1:10200" in both.message
    assert details.rule_key != both.rule_key
    assert str(details.rule_key).startswith("wyoming_voice_status:")
    assert len(str(details.rule_key)) == len("wyoming_voice_status:") + 16


def test_same_plan_reuses_rule_key_and_session_does_not_cover_another(hermes, monkeypatch):
    first = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    again = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert first.rule_key == again.rule_key
    from tools.approval import approve_session
    from tools.approval_context import get_current_session_key

    approve_session(get_current_session_key(), "plugin_rule:" + first.rule_key)
    allowed, _modified = hermes._dispatch_pre_tool_call_hooks("wyoming_voice_status", {"which": "stt"})
    blocked, _modified = hermes._dispatch_pre_tool_call_hooks("wyoming_voice_status", {"which": "tts"})
    assert allowed is None
    assert blocked and "BLOCKED" in blocked
    monkeypatch.setenv("WYOMING_STT_PORT", "10301")
    moved = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert moved.rule_key != first.rule_key


def test_read_is_silent(hermes):
    other = hermes._get_pre_tool_call_directive_details("transcribe_audio", {"which": "stt"})
    assert other.action is None
    missing = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {})
    assert missing.action is None
    extra = hermes._get_pre_tool_call_directive_details(
        "wyoming_voice_status", {"which": "stt", "host": "10.9.9.9"}
    )
    assert extra.action is None


def test_denied_gate_describes_nothing(hermes):
    bare = status("stt", describe_fn=_boom())
    assert bare["success"] is False
    assert bare.get("isError") is True
    block, _modified = hermes._dispatch_pre_tool_call_hooks("wyoming_voice_status", {"which": "stt"})
    assert block
    assert "BLOCKED" in block


def test_mismatch_after_preview_describes_nothing(hermes, monkeypatch):
    assert hermes._get_pre_tool_call_directive_details(
        "wyoming_voice_status", {"which": "stt"}
    ).action == "approve"
    monkeypatch.setenv("WYOMING_STT_PORT", "10301")
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False
    assert body.get("isError") is True
    assert "changed" in body["error"]


def test_no_private_imports():
    pattern = "|".join(
        [
            "tools\\." + "approval",
            "_" + "yolo" + "_active",
            "approval" + "_context",
            "approval" + "_prompt",
            "request_elicitation_consent",
            "prompt_dangerous_approval",
        ]
    )
    proc = subprocess.run(
        ["grep", "-rnE", pattern, "--include=*.py", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    leaked = [
        line
        for line in proc.stdout.splitlines()
        if "/tests/" not in line and not line.startswith("tests/")
    ]
    assert leaked == [], leaked


def test_preview_for_one_spelling_does_not_cover_another(hermes):
    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"})
    body = status("stt", describe_fn=_boom(), raw={"which": "STT"})
    assert body["success"] is False
    assert body.get("isError") is True


def test_preview_from_another_session_is_not_used(hermes):
    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"}, session_id="other", task_id="t1")
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False


def test_preview_from_another_task_is_not_used(hermes):
    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"}, session_id="s1", task_id="other")
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False


def test_silent_call_rewritten_to_a_write_finds_no_preview(hermes):
    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"})
    assert gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt", "extra": 1}) is None
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False
    assert body.get("isError") is True


def test_old_preview_is_refused(hermes, monkeypatch):
    import time

    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"})
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + 601)
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False
    assert "too old" in body["error"]


def test_matching_preview_describes_once(hermes):
    gate.on_pre_tool_call("wyoming_voice_status", {"which": "stt"})
    seen = []

    def describe(endpoint, **_kwargs):
        seen.append(endpoint.label)
        return {"asr": [{"name": "tiny", "installed": True, "languages": ["en"]}], "tts": []}

    body = status("stt", describe_fn=describe, raw={"which": "stt"})
    assert body["success"] is True
    assert seen == ["127.0.0.1:10300"]
    again = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert again["success"] is False


def test_host_process_blocks_and_does_not_describe(hermes, monkeypatch):
    monkeypatch.setenv("HERMES_PLUGIN_HOST_PROCESS", "1")
    details = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    assert details.action == "block"
    assert details.message == host_process_blocked()
    body = status("stt", describe_fn=_boom(), raw={"which": "stt"})
    assert body["success"] is False
    assert body["error"] == host_process_blocked()


def test_overlong_question_blocks_without_asking(hermes, monkeypatch):
    monkeypatch.setenv("WYOMING_STT_HOST", _long_host("a"))
    monkeypatch.setenv("WYOMING_TTS_HOST", _long_host("e"))
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    monkeypatch.setenv("WYOMING_TTS_PORT", "10200")
    details = hermes._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "both"})
    assert details.action == "block"
    assert details.message == approval_too_long()
    body = status("both", describe_fn=_boom(), raw={"which": "both"})
    assert body["success"] is False
    one = gate.approval_text(["127.0.0.1:10300"])
    both = gate.approval_text(["127.0.0.1:10300", "10.1.1.8:10200"])
    assert len(one) <= APPROVAL_TEXT_MAX
    assert len(both) <= APPROVAL_TEXT_MAX
    assert "10.1.1.8:10200" in both


def test_register_installs_the_hook():
    import importlib.util
    import types

    plugin_root = str(ROOT)
    saved_path = list(sys.path)
    saved_providers = sys.modules.get("providers")
    if plugin_root in sys.path:
        sys.path.remove(plugin_root)
    sys.path.insert(0, plugin_root)
    if saved_providers is not None and not str(getattr(saved_providers, "__file__", "")).startswith(plugin_root):
        sys.modules.pop("providers", None)
    agent = sys.modules.get("agent") or types.ModuleType("agent")
    sys.modules["agent"] = agent
    for module_name, class_name in (
        ("transcription_provider", "TranscriptionProvider"),
        ("tts_provider", "TTSProvider"),
    ):
        key = f"agent.{module_name}"
        module = sys.modules.get(key) or types.ModuleType(key)
        if not hasattr(module, class_name):
            setattr(module, class_name, type(class_name, (), {}))
        sys.modules[key] = module
        setattr(agent, module_name, module)
    try:
        spec = importlib.util.spec_from_file_location("wyoming_hook_plugin", ROOT / "__init__.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        class Ctx:
            def __init__(self):
                self.hooks = {}

            def register_transcription_provider(self, provider):
                self.stt = provider

            def register_tts_provider(self, provider):
                self.tts = provider

            def register_tool(self, **kwargs):
                self.handler = kwargs["handler"]

            def register_hook(self, name, callback):
                self.hooks.setdefault(name, []).append(callback)

            def register_skill(self, *args, **kwargs):
                return None

        ctx = Ctx()
        module.register(ctx)
        hooked = ctx.hooks.get("pre_tool_call") or []
        assert len(hooked) == 1
        assert hooked[0].__name__ == "on_pre_tool_call"
    finally:
        sys.path[:] = saved_path
        if saved_providers is not None:
            sys.modules["providers"] = saved_providers


def test_approval_text_stays_one_line():
    text = gate.approval_text(["127.0.0.1:10300"])
    assert "\n" not in text
    assert os.linesep not in text
