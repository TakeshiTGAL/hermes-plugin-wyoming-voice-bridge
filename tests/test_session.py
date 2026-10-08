import asyncio
import logging
import wave
from pathlib import Path

import pytest

from endpoints import parse_endpoint
from messages import CONNECT_TIMEOUT_S
from session import BridgeError, describe_sync, synthesize_sync, transcribe_sync
from tests.fake_server import FakeWyoming

INFO = {
    "asr": [{
        "name": "whisper",
        "models": [{
            "name": "tiny-int8",
            "languages": ["en", "ja"],
            "installed": True,
        }],
    }],
    "tts": [{
        "name": "piper",
        "voices": [{
            "name": "en_US-lessac-medium",
            "languages": ["en"],
            "speakers": [{"name": "lessac"}],
            "installed": True,
        }],
    }],
}


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x01" * 1600)


async def _serve(reader, writer, *, pause=0, mode="ok", text=""):
    from wyoming.event import Event, async_read_event, async_write_event

    event = await async_read_event(reader)
    if event is None:
        writer.close()
        return
    if event.type == "describe":
        if mode == "error":
            await async_write_event(Event(type="error", data={"text": "nope", "code": "not-found"}), writer)
        elif mode == "hang":
            await asyncio.sleep(pause)
        elif mode == "garbage":
            writer.write(b"this is not json\n")
            await writer.drain()
        else:
            await async_write_event(Event(type="info", data=INFO), writer)
        writer.close()
        return
    if event.type == "transcribe":
        while True:
            nxt = await async_read_event(reader)
            if nxt is None or nxt.type == "audio-stop":
                break
        if mode == "drop":
            writer.close()
            return
        await asyncio.sleep(pause)
        await async_write_event(Event(type="transcript", data={"text": text}), writer)
        writer.close()
        return
    if event.type == "synthesize":
        if mode == "drop":
            writer.close()
            return
        if mode == "nostart":
            await async_write_event(Event(type="audio-stop"), writer)
            writer.close()
            return
        await async_write_event(Event(type="audio-start", data={"rate": 16000, "width": 2, "channels": 1}), writer)
        if mode != "empty":
            await async_write_event(
                Event(type="audio-chunk", data={"rate": 16000, "width": 2, "channels": 1}, payload=b"\x00\x00" * 800),
                writer,
            )
        await async_write_event(Event(type="audio-stop"), writer)
        writer.close()


def test_describe_and_empty_transcript_are_distinct(tmp_path, caplog):
    caplog.set_level(logging.INFO)
    secret = "secret phrase should stay out of logs"

    async def handler(reader, writer):
        await _serve(reader, writer, text=secret)

    wav = tmp_path / "in.wav"
    _wav(wav)
    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        summary = describe_sync(endpoint, connect_timeout=1, budget=3)
        assert summary["asr"][0]["name"] == "tiny-int8"
        heard = transcribe_sync(endpoint, str(wav), model="tiny-int8", language="en", connect_timeout=1, budget=3)
    assert heard == secret
    assert secret not in caplog.text
    assert "payload_bytes=" in caplog.text


def test_silence_longer_than_connect_timeout_still_returns(tmp_path):
    async def handler(reader, writer):
        await _serve(reader, writer, pause=CONNECT_TIMEOUT_S + 1, text="ok")

    wav = tmp_path / "in.wav"
    _wav(wav)
    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        heard = transcribe_sync(
            endpoint, str(wav), model=None, language=None,
            connect_timeout=CONNECT_TIMEOUT_S, budget=CONNECT_TIMEOUT_S + 4,
        )
    assert heard == "ok"


def test_server_error_event_is_not_success():
    async def handler(reader, writer):
        await _serve(reader, writer, mode="error")

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            describe_sync(endpoint, connect_timeout=1, budget=3)
    assert "not-found" in caught.value.message
    assert "secret" not in caught.value.message


def test_non_json_line_is_not_a_closed_connection():
    async def handler(reader, writer):
        await _serve(reader, writer, mode="garbage")

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            describe_sync(endpoint, connect_timeout=1, budget=3)
    assert "not JSON" in caught.value.message
    assert "closed the connection" not in caught.value.message


def test_dropped_connection_is_not_a_transcript(tmp_path):
    async def handler(reader, writer):
        await _serve(reader, writer, mode="drop")

    wav = tmp_path / "in.wav"
    _wav(wav)
    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            transcribe_sync(endpoint, str(wav), connect_timeout=1, budget=3)
    assert caught.value.maybe_started
    assert "closed the connection" in caught.value.message


def test_stop_without_audio_start_is_empty_audio_not_a_format_error():
    async def handler(reader, writer):
        await _serve(reader, writer, mode="nostart")

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            synthesize_sync(endpoint, "hello", voice=None, speaker=None, connect_timeout=1, budget=3)
    assert "no audio" in caught.value.message
    assert "16-bit" not in caught.value.message


def test_empty_audio_is_not_a_file(tmp_path):
    async def handler(reader, writer):
        await _serve(reader, writer, mode="empty")

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        with pytest.raises(BridgeError) as caught:
            synthesize_sync(endpoint, "hello", voice=None, speaker=None, connect_timeout=1, budget=3)
    assert "no audio" in caught.value.message
    assert list(tmp_path.iterdir()) == []


def test_synthesize_returns_pcm_without_writing():
    async def handler(reader, writer):
        await _serve(reader, writer)

    with FakeWyoming(handler) as server:
        endpoint = parse_endpoint("127.0.0.1", str(server.port))
        rate, width, channels, pcm = synthesize_sync(
            endpoint, "hello", voice="en_US-lessac-medium", speaker=None, connect_timeout=1, budget=3,
        )
    assert (rate, width, channels) == (16000, 2, 1)
    assert pcm


def test_open_drops_any_read_timeout_the_library_sets(monkeypatch):
    import wyoming.client as client
    from endpoints import parse_endpoint
    from session import _open

    seen = {}

    class FakeClient:
        def __init__(self) -> None:
            self.read_timeout = None

        @classmethod
        def from_uri(cls, uri: str, **kwargs: object) -> "FakeClient":
            seen["uri"] = uri
            seen["kwargs"] = kwargs
            return cls()

        async def connect(self) -> None:
            self.read_timeout = 5

    monkeypatch.setattr(client.AsyncClient, "from_uri", FakeClient.from_uri)
    opened = asyncio.run(_open(parse_endpoint("127.0.0.1", "10300"), 5))
    assert seen["kwargs"] == {}
    assert seen["uri"] == "tcp://127.0.0.1:10300"
    assert opened.read_timeout is None


def test_connect_timeout_is_five_seconds_and_refused_port_fails():
    assert CONNECT_TIMEOUT_S == 5
    endpoint = parse_endpoint("127.0.0.1", "1")
    with pytest.raises(BridgeError) as caught:
        describe_sync(endpoint, connect_timeout=1, budget=2)
    assert "Could not connect" in caught.value.message
    assert "not sent again" in caught.value.message or "Nothing was retried" in caught.value.message
