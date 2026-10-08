import json
import os
import wave
from pathlib import Path

import pytest

from endpoints import Endpoint
from service import status, synthesize_to, transcribe_file


INFO = {
    "asr": [{
        "program": "whisper",
        "name": "tiny-int8",
        "languages": ["en"],
        "installed": True,
    }],
    "tts": [{
        "program": "piper",
        "name": "en_US-lessac-medium",
        "languages": ["en"],
        "speakers": ["lessac"],
        "installed": True,
    }],
}


def _endpoint():
    return Endpoint("127.0.0.1", 10300)


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x01" * 800)


def _set_env(monkeypatch):
    monkeypatch.setenv("WYOMING_STT_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    monkeypatch.setenv("WYOMING_TTS_HOST", "10.1.1.8")
    monkeypatch.setenv("WYOMING_TTS_PORT", "10200")


def test_language_must_match_a_listed_code_exactly(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    sent = []
    wav = tmp_path / "in.wav"
    _wav(wav)

    def describe(_endpoint, **_kwargs):
        return {"asr": INFO["asr"], "tts": []}

    def transcribe(*_args, **kwargs):
        sent.append(kwargs.get("language"))
        return "ok"

    refused = transcribe_file(
        str(wav), language="en-US", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert refused["success"] is False
    assert "Language 'en-US'" in refused["error"]
    assert "No audio was sent" in refused["error"]
    assert "closed the connection" not in refused["error"]
    assert "wyoming_voice_status" in refused["error"]
    assert "case-sensitive" in refused["error"]
    assert sent == []

    hyphen = {
        "asr": [{
            "program": "whisper",
            "name": "tiny-int8",
            "languages": ["en-US"],
            "installed": True,
        }],
        "tts": [],
    }

    def describe_hyphen(_endpoint, **_kwargs):
        return hyphen

    matched = transcribe_file(
        str(wav), language="en_US", describe_fn=describe_hyphen, transcribe_fn=transcribe,
    )
    assert matched["success"] is True
    assert sent == ["en-US"]


def test_unnamed_model_sends_a_language_only_when_every_model_lists_it(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    sent = []
    wav = tmp_path / "in.wav"
    _wav(wav)
    both = {
        "asr": [
            {"program": "whisper", "name": "tiny", "languages": ["en"], "installed": True},
            {"program": "whisper", "name": "small", "languages": ["en", "ja"], "installed": True},
        ],
        "tts": [],
    }

    def describe(_endpoint, **_kwargs):
        return both

    def transcribe(*_args, **kwargs):
        sent.append(kwargs.get("language"))
        return "ok"

    refused = transcribe_file(
        str(wav), language="ja", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert refused["success"] is False
    assert "no model was named" in refused["error"]
    assert "Name a model and try again" in refused["error"]
    assert "No audio was sent" in refused["error"]
    assert "wyoming_voice_status" in refused["error"]
    assert "case-sensitive" in refused["error"]
    assert sent == []

    named = transcribe_file(
        str(wav), model="small", language="ja", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert named["success"] is True
    assert sent == ["ja"]

    shared = transcribe_file(
        str(wav), language="en", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert shared["success"] is True
    assert sent == ["ja", "en"]


def test_speakers_over_fifty_are_marked(monkeypatch):
    _set_env(monkeypatch)
    row = dict(INFO["tts"][0])
    row["speakers"] = [f"s{i}" for i in range(51)]

    def describe(_endpoint, **_kwargs):
        return {"asr": [], "tts": [row]}

    body = status("tts", describe_fn=describe, approver=lambda _targets: None)
    shown = body["tts"]["models"][0]
    assert len(shown["speakers"]) == 50
    assert shown["speakers_truncated"] is True


def test_fifty_speakers_are_not_marked_truncated(monkeypatch):
    _set_env(monkeypatch)
    row = dict(INFO["tts"][0])
    row["speakers"] = [f"s{i}" for i in range(50)]

    def describe(_endpoint, **_kwargs):
        return {"asr": [], "tts": [row]}

    body = status("tts", describe_fn=describe, approver=lambda _targets: None)
    shown = body["tts"]["models"][0]
    assert len(shown["speakers"]) == 50
    assert "speakers_truncated" not in shown


def test_missing_installed_counts_as_installed(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    row = {"program": "whisper", "name": "tiny-int8", "languages": ["en"]}
    sent = []
    wav = tmp_path / "in.wav"
    _wav(wav)

    def describe(_endpoint, **_kwargs):
        return {"asr": [row], "tts": []}

    def transcribe(*_args, **_kwargs):
        sent.append("audio")
        return "ok"

    body = status("stt", describe_fn=describe, approver=lambda _targets: None)
    assert body["stt"]["ready"] is True
    assert body["stt"]["models"][0]["installed"] is True
    result = transcribe_file(str(wav), describe_fn=describe, transcribe_fn=transcribe)
    assert result["success"] is True
    assert sent == ["audio"]


def test_describe_timeout_says_the_server_may_be_working():
    from messages import describe_timeout

    text = describe_timeout("127.0.0.1:10300")
    assert "may already be working" in text
    assert "It was not sent again" in text
    assert "Check the server before you try again" in text
    assert "retry now" not in text.lower()


def test_unknown_model_sends_no_audio(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    sent = []

    def describe(_endpoint, **_kwargs):
        return {"asr": INFO["asr"], "tts": []}

    def transcribe(*_args, **_kwargs):
        sent.append("audio")
        return "nope"

    wav = tmp_path / "in.wav"
    _wav(wav)
    result = transcribe_file(str(wav), model="nope", describe_fn=describe, transcribe_fn=transcribe)
    assert result["success"] is False
    assert result["transcript"] == ""
    assert "not in the server" in result["error"]
    assert "wyoming_voice_status" in result["error"]
    assert "case-sensitive" in result["error"]
    assert sent == []


def test_empty_transcript_is_success_and_disconnect_is_not(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)

    def describe(_endpoint, **_kwargs):
        return {"asr": INFO["asr"], "tts": []}

    ok = transcribe_file(
        str(wav), describe_fn=describe, transcribe_fn=lambda *_a, **_k: "",
    )
    assert ok == {"success": True, "transcript": "", "provider": "wyoming"}

    def boom(*_a, **_k):
        from session import BridgeError
        raise BridgeError("The Wyoming speech recognition server closed the connection before a finished reply. Nothing was kept and nothing was retried.", maybe_started=True)

    bad = transcribe_file(str(wav), describe_fn=describe, transcribe_fn=boom)
    assert bad["success"] is False
    assert bad["transcript"] == ""
    assert "closed the connection" in bad["error"]


def test_both_is_not_success_when_one_side_fails(monkeypatch):
    _set_env(monkeypatch)
    calls = []

    def describe(endpoint, **_kwargs):
        calls.append(endpoint.port)
        if endpoint.port == 10200:
            from session import BridgeError
            raise BridgeError("Could not connect to Wyoming server at 10.1.1.8:10200 within 5s. Nothing was retried.")
        return {"asr": INFO["asr"], "tts": []}

    body = status("both", describe_fn=describe, approver=lambda _targets: None)
    assert body["success"] is False
    assert body["stt"]["success"] is True
    assert body["tts"]["success"] is False
    assert calls  # approval returned None before describe


def test_bad_which_does_not_ask_approval(monkeypatch):
    _set_env(monkeypatch)
    asked = []
    body = status("everywhere", approver=lambda targets: asked.append(targets) or None)
    assert body["success"] is False
    assert asked == []
    assert "stt, tts, or both" in body["error"]


def test_denied_approval_does_not_describe(monkeypatch):
    _set_env(monkeypatch)
    called = []
    body = status("stt", describe_fn=lambda *_a, **_k: called.append(1), approver=lambda _t: "BLOCKED: no")
    assert called == []
    assert body["success"] is False


def test_speech_timeout_text(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)

    def describe(_endpoint, **_kwargs):
        return {"asr": INFO["asr"], "tts": []}

    def transcribe(*_a, **_k):
        from session import BridgeError
        from messages import speech_timeout
        raise BridgeError(speech_timeout("speech recognition", "127.0.0.1:10300", 120), maybe_started=True)

    result = transcribe_file(str(wav), describe_fn=describe, transcribe_fn=transcribe)
    assert result["success"] is False
    assert "may already be transcribing" in result["error"]
    assert "try again yourself" not in result["error"].lower() or "before you try again" in result["error"]
    assert "Check the server before you try again" in result["error"]


def test_voice_not_listed_does_not_synthesize(tmp_path, monkeypatch):
    _set_env(monkeypatch)
    written = []

    def describe(_endpoint, **_kwargs):
        return {"asr": [], "tts": INFO["tts"]}

    def synthesize(*_a, **_k):
        written.append(1)
        return (16000, 2, 1, b"\x00\x00")

    with pytest.raises(Exception) as caught:
        synthesize_to("Hello.", str(tmp_path / "out.wav"), voice="other", describe_fn=describe, synthesize_fn=synthesize)
    assert written == []
    assert "not in the server" in str(caught.value)
    assert "wyoming_voice_status" in str(caught.value)
    assert "case-sensitive" in str(caught.value)


def test_wav_is_replaced_only_after_audio(tmp_path, monkeypatch):
    _set_env(monkeypatch)

    def describe(_endpoint, **_kwargs):
        return {"asr": [], "tts": INFO["tts"]}

    def synthesize(*_a, **_k):
        return (16000, 2, 1, b"\x01\x00" * 400)

    def guard(_path):
        return None

    dest = tmp_path / "reply.mp3"
    written = synthesize_to(
        "Hello.", str(dest), voice="en_US-lessac-medium",
        describe_fn=describe, synthesize_fn=synthesize,
        writer=lambda path, rate, width, channels, pcm: __import__("audiofiles").write_wav(
            path, rate, width, channels, pcm, guard=guard,
        ),
    )
    assert written.endswith(".wav")
    assert Path(written).stat().st_size > 44
    assert not dest.exists()


def test_register_does_nothing_without_hermes_methods():
    from __init__ import register

    class Ctx:
        pass

    register(Ctx())


def test_tool_ignores_a_host_argument(monkeypatch):
    _set_env(monkeypatch)
    seen = []

    def describe(endpoint, **_kwargs):
        seen.append((endpoint.host, endpoint.port))
        return {"asr": INFO["asr"], "tts": []}

    from __init__ import register

    class Ctx:
        def register_transcription_provider(self, *_a, **_k):
            raise AssertionError("providers need Hermes")

        def register_tts_provider(self, *_a, **_k):
            return None

        def register_tool(self, **kwargs):
            self.handler = kwargs["handler"]

    # register imports providers, which imports Hermes. Skip that path and call status.
    body = json.loads(__import__("json").dumps(
        status("stt", describe_fn=describe, approver=lambda _t: None)
    ))
    assert seen == [("127.0.0.1", 10300)]
    assert body["stt"]["host"] == "127.0.0.1"
    assert "10.9.9.9" not in json.dumps(body)
