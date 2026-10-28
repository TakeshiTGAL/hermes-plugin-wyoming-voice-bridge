"""WYOMING_* settings come from the active Hermes profile, not from a value another profile left in the environment."""
import json
import re
from pathlib import Path

import pytest

from endpoints import Endpoint, endpoint_from_env, setting
from service import configured

ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "WYOMING_STT_HOST",
    "WYOMING_STT_PORT",
    "WYOMING_TTS_HOST",
    "WYOMING_TTS_PORT",
    "WYOMING_STT_MODEL",
    "WYOMING_TTS_VOICE",
)
_ENV_READ = re.compile(
    r"""os\s*\.\s*(?:getenv\s*\(|environ\s*\.\s*get\s*\(|environ\s*\[\s*)\s*['"]WYOMING_"""
)


def _other_profile_env(monkeypatch):
    monkeypatch.setenv("WYOMING_STT_HOST", "other-profile.example")
    monkeypatch.setenv("WYOMING_STT_PORT", "1")
    monkeypatch.setenv("WYOMING_TTS_HOST", "other-profile.example")
    monkeypatch.setenv("WYOMING_TTS_PORT", "2")
    monkeypatch.setenv("WYOMING_TTS_VOICE", "other-voice")


def _release(scope, token):
    if token is not None:
        try:
            scope.reset_secret_scope(token)
        except ValueError:
            pass
    scope.set_secret_scope(None)
    scope.set_multiplex_active(False)


def test_product_code_does_not_read_wyoming_settings_from_environ():
    for path in sorted(ROOT.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert _ENV_READ.search(text) is None, path.name


def test_scope_value_is_used_when_environ_differs(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    _other_profile_env(monkeypatch)
    token = scope.set_secret_scope({
        "WYOMING_STT_HOST": "10.0.0.5",
        "WYOMING_STT_PORT": "10300",
        "WYOMING_TTS_HOST": "speech.lan",
        "WYOMING_TTS_PORT": "10200",
        "WYOMING_TTS_VOICE": "en_US-lessac-medium",
    })
    try:
        stt = endpoint_from_env("WYOMING_STT")
        tts = endpoint_from_env("WYOMING_TTS")
        voice = setting("WYOMING_TTS_VOICE")
    finally:
        _release(scope, token)
    assert stt == Endpoint(host="10.0.0.5", port=10300)
    assert tts == Endpoint(host="speech.lan", port=10200)
    assert voice == "en_US-lessac-medium"


def test_single_profile_without_scope_reads_the_environment(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    scope.set_multiplex_active(False)
    monkeypatch.setenv("WYOMING_STT_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    assert endpoint_from_env("WYOMING_STT") == Endpoint(host="127.0.0.1", port=10300)
    assert configured("WYOMING_STT") is True


def test_multiplex_scope_miss_does_not_read_environ(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    _other_profile_env(monkeypatch)
    scope.set_multiplex_active(True)
    token = scope.set_secret_scope({"UNRELATED": "present"})
    try:
        stt = endpoint_from_env("WYOMING_STT")
        tts_ready = configured("WYOMING_TTS")
        values = {name: setting(name) for name in NAMES}
    finally:
        _release(scope, token)
    assert stt is None
    assert tts_ready is False
    assert values == {name: None for name in NAMES}


def test_unscoped_multiplex_raises_and_is_available_check_is_false(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    _other_profile_env(monkeypatch)
    scope.set_multiplex_active(True)
    token = scope.set_secret_scope(None)
    try:
        with pytest.raises(scope.UnscopedSecretError):
            endpoint_from_env("WYOMING_STT")
        ready = configured("WYOMING_STT")
    finally:
        _release(scope, token)
    assert ready is False


def test_status_tool_asks_about_and_describes_the_scope_server(monkeypatch):
    scope = pytest.importorskip("agent.secret_scope")
    import service

    _other_profile_env(monkeypatch)
    asked = []
    described = []

    def approver(targets):
        asked.append(list(targets))
        return None

    def describe(endpoint, **_kwargs):
        described.append(endpoint.label)
        return {"asr": [], "tts": []}

    token = scope.set_secret_scope({
        "WYOMING_STT_HOST": "10.0.0.5",
        "WYOMING_STT_PORT": "10300",
    })
    try:
        body = service.status("stt", describe_fn=describe, approver=approver)
    finally:
        _release(scope, token)
    assert asked == [["10.0.0.5:10300"]]
    assert described == ["10.0.0.5:10300"]
    assert "other-profile.example" not in json.dumps(body)
