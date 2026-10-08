"""Offline checks from the frozen acceptance table that the older files did not cover."""
import inspect
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import traceback
import wave
from pathlib import Path

import pytest

from audiofiles import load_pcm_wav, write_wav
from endpoints import EndpointError, parse_endpoint
from messages import (
    DESCRIBE_TIMEOUT_S,
    FFMPEG_MAX_SECONDS,
    FFMPEG_TIMEOUT_S,
    MAX_AUDIO_BYTES,
    MAX_PCM_BYTES,
    MAX_TEXT_CHARS,
    audio_too_large,
    input_pcm_too_large,
    pcm_too_large,
)
from service import status, synthesize_to, transcribe_file
from session import BridgeError, describe, describe_sync, summarize_info
from tests.fake_server import FakeWyoming


def _wav(path: Path, rate: int = 16000, frames: int = 800) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x01" * frames)


def _env(monkeypatch) -> None:
    monkeypatch.setenv("WYOMING_STT_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    monkeypatch.setenv("WYOMING_TTS_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_TTS_PORT", "10200")


def _asr(name: str = "tiny-int8", languages: list[str] | None = None, installed: object = True) -> dict:
    row = {"program": "whisper", "name": name, "languages": languages if languages is not None else ["en"]}
    if installed is not ...:
        row["installed"] = installed
    return row


def _claim_large_wav(path: Path) -> None:
    """A short file whose WAV header claims more than 20 MiB of PCM frames."""
    nframes = (MAX_PCM_BYTES // 2) + 1
    claimed = nframes * 2
    fmt = struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)
    actual = b"\x00\x00" * 8
    body = b"fmt " + struct.pack("<I", 16) + fmt + b"data" + struct.pack("<I", claimed) + actual
    path.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def test_notice_quotes_the_upstream_copyright_line():
    text = Path(__file__).resolve().parents[1].joinpath("NOTICE").read_text(encoding="utf-8")
    assert "\nCopyright (c) 2023 Michael Hansen\n" in f"\n{text}"


def test_register_source_does_not_import_tests():
    source = Path(__file__).resolve().parents[1].joinpath("__init__.py").read_text(encoding="utf-8")
    assert "import tests" not in source
    assert "from tests" not in source


def test_public_address_is_accepted_and_a_bad_host_does_not_connect(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("socket")

    monkeypatch.setattr(socket.socket, "connect", explode)
    got = parse_endpoint("8.8.8.8", "53")
    assert got.host == "8.8.8.8"
    assert got.port == 53
    with pytest.raises(EndpointError):
        parse_endpoint("[::1]", "10300")
    label = "a" * 63
    host = ".".join((label, label, label, "b" * 61))
    assert len(host) == 253
    assert parse_endpoint(host, "1").host == host
    with pytest.raises(EndpointError):
        parse_endpoint(host + "c", "1")


def test_is_available_is_address_shape_not_a_live_server(monkeypatch):
    import sys
    import types

    agent = sys.modules.get("agent") or types.ModuleType("agent")
    sys.modules["agent"] = agent
    for module_name, class_name in (
        ("transcription_provider", "TranscriptionProvider"),
        ("tts_provider", "TTSProvider"),
    ):
        key = f"agent.{module_name}"
        if key not in sys.modules:
            module = types.ModuleType(key)
            setattr(module, class_name, type(class_name, (), {}))
            sys.modules[key] = module
            setattr(agent, module_name, module)
    from providers import build_providers

    def explode(*_args, **_kwargs):
        raise AssertionError("socket")

    monkeypatch.setattr(socket.socket, "connect", explode)
    monkeypatch.setenv("WYOMING_STT_HOST", "8.8.8.8")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    stt, _tts = build_providers()
    assert stt.is_available() is True
    rows = stt.list_models()
    assert rows == [{
        "id": "default",
        "display": "Wyoming server. Not a live catalog; call wyoming_voice_status.",
    }]
    monkeypatch.setenv("WYOMING_STT_HOST", "http://127.0.0.1")
    assert stt.is_available() is False
    assert stt.list_models() == []
    monkeypatch.setenv("WYOMING_STT_HOST", "")
    monkeypatch.setenv("WYOMING_STT_PORT", "")
    assert stt.is_available() is False


def test_tool_handler_keeps_the_env_host(monkeypatch):
    import service
    from __init__ import register
    from tests.test_language import _stub_bases

    _stub_bases()
    _env(monkeypatch)
    seen = []

    def describe(endpoint, **_kwargs):
        seen.append((endpoint.host, endpoint.port))
        return {"asr": [_asr()], "tts": []}

    monkeypatch.setitem(service.status.__kwdefaults__, "describe_fn", describe)
    monkeypatch.setitem(service.status.__kwdefaults__, "approver", lambda _targets: None)

    class Ctx:
        def register_transcription_provider(self, provider):
            self.stt = provider

        def register_tts_provider(self, provider):
            self.tts = provider

        def register_tool(self, **kwargs):
            self.handler = kwargs["handler"]

    ctx = Ctx()
    register(ctx)
    import json
    body = json.loads(ctx.handler({"which": "stt", "host": "10.9.9.9", "port": "9"}))
    assert seen == [("127.0.0.1", 10300)]
    assert body["stt"]["host"] == "127.0.0.1"


def test_speech_path_does_not_ask_for_approval(tmp_path, monkeypatch):
    _env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)

    def boom(*_args, **_kwargs):
        raise AssertionError("approval")

    monkeypatch.setattr("service.approve_describe", boom)
    result = transcribe_file(
        str(wav),
        describe_fn=lambda *_a, **_k: {"asr": [_asr()], "tts": []},
        transcribe_fn=lambda *_a, **_k: "ok",
    )
    assert result["success"] is True


def test_missing_host_is_refused_before_approval(monkeypatch):
    monkeypatch.delenv("WYOMING_STT_HOST", raising=False)
    monkeypatch.delenv("WYOMING_STT_PORT", raising=False)
    asked = []

    def describe(*_args, **_kwargs):
        raise AssertionError("describe")

    body = status("stt", describe_fn=describe, approver=lambda targets: asked.append(targets) or None)
    assert asked == []
    assert body["success"] is False


def test_installed_false_is_not_a_candidate_and_null_is(tmp_path, monkeypatch):
    _env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)
    sent = []
    rows = [
        _asr("tiny-int8", ["en"], False),
        _asr("small", ["ja"], None),
    ]

    def describe(_endpoint, **_kwargs):
        return {"asr": rows, "tts": []}

    def transcribe(*_args, **kwargs):
        sent.append(kwargs.get("model"))
        return "ok"

    body = status("stt", describe_fn=describe, approver=lambda _targets: None)
    listed = {row["name"]: row["installed"] for row in body["stt"]["models"]}
    assert listed == {"tiny-int8": False, "small": True}
    assert body["stt"]["ready"] is True
    refused = transcribe_file(
        str(wav), model="Tiny-int8", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert refused["success"] is False
    assert "Tiny-int8" in refused["error"]
    assert "wyoming_voice_status" in refused["error"]
    assert sent == []
    named = transcribe_file(
        str(wav), model="small", language="ja", describe_fn=describe, transcribe_fn=transcribe,
    )
    assert named["success"] is True
    assert sent == ["small"]
    only_false = transcribe_file(
        str(wav),
        describe_fn=lambda *_a, **_k: {"asr": [_asr("tiny-int8", ["en"], False)], "tts": []},
        transcribe_fn=transcribe,
    )
    assert only_false["success"] is False
    assert "no installed" in only_false["error"]
    assert sent == ["small"]


def test_languages_over_two_hundred_are_marked(monkeypatch):
    _env(monkeypatch)

    def describe(count):
        row = _asr(languages=[f"l{i}" for i in range(count)])

        def inner(_endpoint, **_kwargs):
            return {"asr": [row], "tts": []}

        return inner

    marked = status("stt", describe_fn=describe(201), approver=lambda _t: None)
    item = marked["stt"]["models"][0]
    assert len(item["languages"]) == 200
    assert item["languages_truncated"] is True
    exact = status("stt", describe_fn=describe(200), approver=lambda _t: None)
    assert len(exact["stt"]["models"][0]["languages"]) == 200
    assert "languages_truncated" not in exact["stt"]["models"][0]


def test_empty_and_default_names_are_not_sent(tmp_path, monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("WYOMING_STT_MODEL", "default")
    monkeypatch.setenv("WYOMING_TTS_VOICE", "")
    wav = tmp_path / "in.wav"
    _wav(wav)
    seen = []

    def transcribe(*_args, **kwargs):
        seen.append((kwargs.get("model"), kwargs.get("language")))
        return "ok"

    result = transcribe_file(
        str(wav),
        model="",
        language="default",
        describe_fn=lambda *_a, **_k: {"asr": [_asr()], "tts": []},
        transcribe_fn=transcribe,
    )
    assert result["success"] is True
    assert seen == [(None, None)]
    spoken = []

    def synthesize(*_args, **kwargs):
        spoken.append(kwargs.get("voice"))
        return (16000, 2, 1, b"\x00\x01" * 8)

    path = synthesize_to(
        "Hello.",
        str(tmp_path / "out.wav"),
        voice="default",
        describe_fn=lambda *_a, **_k: {"asr": [], "tts": [_asr("en_US-lessac-medium", ["en"])]},
        synthesize_fn=synthesize,
        writer=lambda path, rate, width, channels, pcm: write_wav(
            path, rate, width, channels, pcm, guard=lambda _p: None,
        ),
    )
    assert spoken == [None]
    assert path.endswith(".wav")


def test_text_limits_stop_before_connect(tmp_path, monkeypatch):
    _env(monkeypatch)
    calls = []

    def describe(*_args, **_kwargs):
        calls.append("describe")
        return {"asr": [], "tts": [_asr("en_US-lessac-medium")]}

    dest = tmp_path / "out.wav"
    with pytest.raises(BridgeError) as empty:
        synthesize_to("   ", str(dest), describe_fn=describe)
    assert calls == []
    assert not dest.exists()
    assert "Nothing was sent" in empty.value.message
    with pytest.raises(BridgeError) as long:
        synthesize_to("a" * (MAX_TEXT_CHARS + 1), str(dest), describe_fn=describe)
    assert calls == []
    assert "Shorten it and try again" in long.value.message
    synthesize_to(
        "a" * MAX_TEXT_CHARS,
        str(dest),
        describe_fn=describe,
        synthesize_fn=lambda *_a, **_k: (16000, 2, 1, b"\x00\x01" * 8),
        writer=lambda path, rate, width, channels, pcm: write_wav(
            path, rate, width, channels, pcm, guard=lambda _p: None,
        ),
    )
    assert calls == ["describe"]
    assert dest.is_file()


def test_symlink_and_unconvertible_audio_send_nothing(tmp_path, monkeypatch):
    _env(monkeypatch)
    target = tmp_path / "real.wav"
    _wav(target)
    link = tmp_path / "link.wav"
    link.symlink_to(target)
    calls = []

    def describe(*_args, **_kwargs):
        calls.append("describe")
        return {"asr": [_asr()], "tts": []}

    refused = transcribe_file(str(link), describe_fn=describe, transcribe_fn=lambda *_a, **_k: "no")
    assert refused["success"] is False
    assert "symbolic link" in refused["error"]
    assert calls == []
    junk = tmp_path / "clip.flac"
    junk.write_bytes(b"this is not audio")
    again = transcribe_file(str(junk), describe_fn=describe, transcribe_fn=lambda *_a, **_k: "no")
    assert again["success"] is False
    assert calls == []
    assert not again["transcript"]


def test_target_wav_does_not_start_ffmpeg_and_conversion_is_an_argv_list(tmp_path, monkeypatch):
    _env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)

    def explode(*_args, **_kwargs):
        raise AssertionError("ffmpeg")

    monkeypatch.setattr("audiofiles.subprocess.run", explode)
    ok = transcribe_file(
        str(wav),
        describe_fn=lambda *_a, **_k: {"asr": [_asr()], "tts": []},
        transcribe_fn=lambda *_a, **_k: "ok",
    )
    assert ok["success"] is True
    monkeypatch.undo()
    other = tmp_path / "slow.wav"
    _wav(other, rate=8000)
    seen = {}
    real = subprocess.run

    def spy(args, **kwargs):
        seen["args"] = args
        seen["timeout"] = kwargs.get("timeout")
        seen["shell"] = kwargs.get("shell")
        return real(args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)
    # load_pcm_wav looks up subprocess.run on its own module.
    monkeypatch.setattr("audiofiles.subprocess.run", spy)
    converted = load_pcm_wav(str(other))
    assert isinstance(seen["args"], list)
    assert seen["args"][0] == shutil.which("ffmpeg")
    assert FFMPEG_MAX_SECONDS == 656
    assert seen["args"][1:4] == ["-y", "-t", str(FFMPEG_MAX_SECONDS)]
    assert "-i" in seen["args"]
    assert seen["args"].index("-t") < seen["args"].index("-i")
    assert seen["shell"] is None
    assert seen["timeout"] == FFMPEG_TIMEOUT_S == 30
    assert converted != str(other)
    os_dir = os.path.dirname(converted)
    shutil.rmtree(os_dir, ignore_errors=True)


def test_file_over_25_mb_does_not_convert_or_connect(tmp_path, monkeypatch):
    _env(monkeypatch)
    # 25 MB in the acceptance table is decimal. 25,000,001 is still under 25 MiB.
    assert MAX_AUDIO_BYTES == 25_000_000
    big = tmp_path / "big.wav"
    fd = os.open(big, os.O_CREAT | os.O_WRONLY)
    os.ftruncate(fd, 25_000_001)
    os.close(fd)
    assert big.stat().st_size < 25 * 1024 * 1024
    calls = []
    result = transcribe_file(
        str(big),
        describe_fn=lambda *_a, **_k: calls.append("describe"),
        transcribe_fn=lambda *_a, **_k: calls.append("audio"),
    )
    assert result["success"] is False
    assert result["error"] == audio_too_large()
    assert calls == []
    assert big.stat().st_size == 25_000_001


def test_wav_header_over_20_mib_sends_no_audio(tmp_path, monkeypatch):
    _env(monkeypatch)
    claimed = tmp_path / "claim.wav"
    _claim_large_wav(claimed)
    assert claimed.stat().st_size < MAX_AUDIO_BYTES
    calls = []
    result = transcribe_file(
        str(claimed),
        describe_fn=lambda *_a, **_k: calls.append("describe"),
        transcribe_fn=lambda *_a, **_k: calls.append("audio"),
    )
    assert result["success"] is False
    assert result["error"] == input_pcm_too_large()
    assert calls == []
    assert claimed.is_file()


def test_small_flac_that_expands_past_20_mib_sends_no_audio(tmp_path, monkeypatch):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail("ffmpeg is not on PATH")
    _env(monkeypatch)
    flac = tmp_path / "long.flac"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "660", "-c:a", "flac", str(flac)],
        check=True,
        timeout=120,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    assert 0 < flac.stat().st_size < MAX_AUDIO_BYTES
    made = []
    grown = {"bytes": 0}
    real_run = subprocess.run

    def spy_run(args, **kwargs):
        result = real_run(args, **kwargs)
        if isinstance(args, list) and args and args[-1].endswith("speech.wav"):
            grown["bytes"] = os.path.getsize(args[-1])
        return result

    monkeypatch.setattr("audiofiles.subprocess.run", spy_run)
    real_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        made.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", spy_mkdtemp)
    audio_bytes = {"n": 0}

    async def handler(reader, writer):
        from wyoming.event import async_read_event

        event = await async_read_event(reader)
        if event is not None and event.type == "transcribe":
            while True:
                nxt = await async_read_event(reader)
                if nxt is None or nxt.type == "audio-stop":
                    break
                if nxt.type == "audio-chunk":
                    payload = nxt.payload if isinstance(nxt.payload, (bytes, bytearray)) else b""
                    audio_bytes["n"] += len(payload)
        writer.close()

    with FakeWyoming(handler) as server:
        monkeypatch.setenv("WYOMING_STT_PORT", str(server.port))
        result = transcribe_file(str(flac))
    assert result["success"] is False
    assert result["error"] == input_pcm_too_large()
    assert audio_bytes["n"] == 0
    assert MAX_PCM_BYTES < grown["bytes"] < 22 * 1024 * 1024
    assert made
    assert all(not Path(path).exists() for path in made)


def test_catalog_of_500_is_allowed_and_501_sends_nothing_else(tmp_path, monkeypatch):
    def models(count, installed=True):
        return [{"name": f"m{i}", "languages": ["en"], "installed": installed} for i in range(count)]

    summarize_info({"asr": [{"name": "whisper", "models": models(500)}], "tts": []})
    with pytest.raises(BridgeError) as caught:
        summarize_info({"asr": [{"name": "whisper", "models": models(501, installed=False)}], "tts": []})
    assert "more than 500" in caught.value.message
    voices = [{"name": f"v{i}", "languages": ["en"], "installed": True} for i in range(501)]
    with pytest.raises(BridgeError) as voices_caught:
        summarize_info({"asr": [], "tts": [{"name": "piper", "voices": voices}]})
    assert "more than 500" in voices_caught.value.message

    _env(monkeypatch)
    wav = tmp_path / "in.wav"
    _wav(wav)
    seen = {"transcribe": 0, "audio": 0}

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is None:
            writer.close()
            return
        if event.type == "describe":
            info = {"asr": [{"name": "whisper", "models": models(501)}], "tts": []}
            await async_write_event(Event(type="info", data=info), writer)
        elif event.type == "transcribe":
            seen["transcribe"] += 1
            while True:
                nxt = await async_read_event(reader)
                if nxt is None or nxt.type == "audio-stop":
                    break
                if nxt.type == "audio-chunk":
                    payload = nxt.payload if isinstance(nxt.payload, (bytes, bytearray)) else b""
                    seen["audio"] += len(payload)
        writer.close()

    with FakeWyoming(handler) as server:
        monkeypatch.setenv("WYOMING_STT_PORT", str(server.port))
        result = transcribe_file(str(wav))
    assert result["success"] is False
    assert "more than 500" in result["error"]
    assert seen == {"transcribe": 0, "audio": 0}


def test_synthesis_over_20_mib_is_not_written(tmp_path, monkeypatch):
    _env(monkeypatch)
    written = []

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is None:
            writer.close()
            return
        if event.type == "describe":
            info = {"tts": [{"name": "piper", "voices": [{
                "name": "lessac", "languages": ["en"], "installed": True,
            }]}]}
            await async_write_event(Event(type="info", data=info), writer)
        elif event.type == "synthesize":
            await async_write_event(
                Event(type="audio-start", data={"rate": 22050, "width": 2, "channels": 1}),
                writer,
            )
            await async_write_event(
                Event(
                    type="audio-chunk",
                    data={"rate": 22050, "width": 2, "channels": 1},
                    payload=b"\x00" * (MAX_PCM_BYTES + 1),
                ),
                writer,
            )
            await async_write_event(Event(type="audio-stop"), writer)
        writer.close()

    with FakeWyoming(handler) as server:
        monkeypatch.setenv("WYOMING_TTS_PORT", str(server.port))
        with pytest.raises(BridgeError) as caught:
            synthesize_to(
                "Hello.",
                str(tmp_path / "out.wav"),
                describe_fn=describe_sync,
                writer=lambda *_a, **_k: written.append("file"),
            )
    assert caught.value.message == pcm_too_large()
    assert written == []
    assert list(tmp_path.iterdir()) == []


def test_partial_pcm_is_not_success(tmp_path, monkeypatch):
    _env(monkeypatch)

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is not None and event.type == "synthesize":
            await async_write_event(
                Event(type="audio-start", data={"rate": 16000, "width": 2, "channels": 1}),
                writer,
            )
            await async_write_event(
                Event(type="audio-chunk", data={"rate": 16000, "width": 2, "channels": 1}, payload=b"\x00\x01" * 4),
                writer,
            )
        writer.close()

    with FakeWyoming(handler) as server:
        monkeypatch.setenv("WYOMING_TTS_PORT", str(server.port))
        with pytest.raises(BridgeError) as caught:
            synthesize_to(
                "Hello.",
                str(tmp_path / "out.wav"),
                describe_fn=lambda *_a, **_k: {"asr": [], "tts": [_asr("lessac")]},
            )
    assert caught.value.maybe_started
    assert "closed the connection" in caught.value.message
    assert list(tmp_path.iterdir()) == []


def test_json_array_is_refused_before_the_library(monkeypatch):
    import wyoming.event as event_mod

    calls = []
    original = event_mod.json.loads

    def spy(text, *args, **kwargs):
        caller = traceback.extract_stack()[-2].filename.replace("\\", "/")
        if caller.endswith("wyoming/event.py"):
            calls.append(text if isinstance(text, bytes) else str(text).encode())
        return original(text, *args, **kwargs)

    monkeypatch.setattr(event_mod.json, "loads", spy)

    async def handler(reader, writer):
        from wyoming.event import async_read_event

        event = await async_read_event(reader)
        if event is not None and event.type == "describe":
            writer.write(b"[1,2]\n")
            await writer.drain()
        writer.close()

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            describe_sync(endpoint, connect_timeout=1, budget=3)
    assert "not an object" in caught.value.message
    assert "not JSON" not in caught.value.message
    assert "closed the connection" not in caught.value.message
    assert not any(item.strip() == b"[1,2]" for item in calls)


def test_describe_default_is_ten_seconds_and_a_short_hang_says_so():
    assert inspect.signature(describe).parameters["budget"].default == DESCRIBE_TIMEOUT_S == 10

    async def handler(reader, writer):
        from wyoming.event import async_read_event

        await async_read_event(reader)
        await __import__("asyncio").sleep(2)
        writer.close()

    started = time.monotonic()
    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            describe_sync(endpoint, connect_timeout=1, budget=0.3)
    assert time.monotonic() - started < 5
    assert "may already be working" in caught.value.message
    assert "not sent again" in caught.value.message


def test_logs_omit_words_and_pcm(tmp_path, monkeypatch, caplog):
    import logging

    caplog.set_level(logging.INFO)
    secret = "secret phrase should stay out of logs"
    _env(monkeypatch)

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is not None and event.type == "synthesize":
            await async_write_event(
                Event(type="audio-start", data={"rate": 16000, "width": 2, "channels": 1}),
                writer,
            )
            await async_write_event(
                Event(type="audio-chunk", data={"rate": 16000, "width": 2, "channels": 1}, payload=b"\x10\x20" * 4),
                writer,
            )
            await async_write_event(Event(type="audio-stop"), writer)
        writer.close()

    with FakeWyoming(handler) as server:
        monkeypatch.setenv("WYOMING_TTS_PORT", str(server.port))
        synthesize_to(
            secret,
            str(tmp_path / "out.wav"),
            describe_fn=lambda *_a, **_k: {"asr": [], "tts": [_asr("lessac")]},
            writer=lambda path, rate, width, channels, pcm: write_wav(
                path, rate, width, channels, pcm, guard=lambda _p: None,
            ),
        )
    assert secret not in caplog.text
    assert "payload_bytes=" in caplog.text
    assert "1020" not in caplog.text


def test_write_refuses_an_existing_temp_a_missing_parent_and_approval(tmp_path):
    from audiofiles import _write_guard

    dest = tmp_path / "out.wav"
    temp = tmp_path / ".out.wav.wyoming-tmp"
    temp.write_bytes(b"leave-me")
    with pytest.raises(BridgeError) as caught:
        write_wav(str(dest), 16000, 2, 1, b"\x00\x01" * 8, guard=lambda _p: None)
    assert "temporary file" in caught.value.message
    assert "did not replace it" in caught.value.message
    assert "deletes it" not in caught.value.message
    assert temp.read_bytes() == b"leave-me"
    assert not dest.exists()

    missing = tmp_path / "missing" / "out.wav"
    with pytest.raises(BridgeError) as parent:
        write_wav(str(missing), 16000, 2, 1, b"\x00\x01" * 8, guard=lambda _p: None)
    assert "does not exist" in parent.value.message
    assert not missing.parent.exists()

    asked = []

    def guard(path):
        asked.append(path)
        _write_guard(path, lambda: (lambda _p: False, lambda _p: True))

    blocked = tmp_path / "blocked.wav"
    with pytest.raises(BridgeError) as approval:
        write_wav(str(blocked), 16000, 2, 1, b"\x00\x01" * 8, guard=guard)
    assert "Refusing to write" in approval.value.message
    assert not blocked.exists()
    assert asked
