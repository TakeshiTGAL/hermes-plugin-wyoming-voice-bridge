"""One Wyoming TCP exchange. The connect timeout is not left on the socket."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any, Awaitable, Callable

if __package__:
    from .endpoints import Endpoint, tcp_uri
    from .messages import (
        CONNECT_TIMEOUT_S,
        DESCRIBE_TIMEOUT_S,
        MAX_CATALOG,
        MAX_PCM_BYTES,
        STT_TIMEOUT_S,
        TTS_TIMEOUT_S,
        bad_audio_format,
        catalog_too_large,
        connect_failed,
        describe_timeout,
        disconnected,
        empty_audio,
        library_missing,
        not_an_object,
        pcm_too_large,
        server_error,
        speech_timeout,
        unexpected_event,
        unreadable_line,
    )
else:
    from endpoints import Endpoint, tcp_uri
    from messages import (
        CONNECT_TIMEOUT_S,
        DESCRIBE_TIMEOUT_S,
        MAX_CATALOG,
        MAX_PCM_BYTES,
        STT_TIMEOUT_S,
        TTS_TIMEOUT_S,
        bad_audio_format,
        catalog_too_large,
        connect_failed,
        describe_timeout,
        disconnected,
        empty_audio,
        library_missing,
        not_an_object,
        pcm_too_large,
        server_error,
        speech_timeout,
        unexpected_event,
        unreadable_line,
    )

log = logging.getLogger("wyoming_voice_bridge")


class BridgeError(Exception):
    def __init__(self, message: str, *, maybe_started: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.maybe_started = maybe_started


def _import_wyoming() -> Any:
    try:
        import wyoming.client as client
        import wyoming.error as error
        import wyoming.event as event
    except Exception as exc:
        raise BridgeError(library_missing()) from exc
    return client, error, event


def _log_event(event: Any) -> None:
    payload = getattr(event, "payload", None)
    size = len(payload) if isinstance(payload, (bytes, bytearray)) else 0
    log.info("wyoming event %s payload_bytes=%s", getattr(event, "type", "?"), size)


async def _open(endpoint: Endpoint, connect_timeout: float) -> Any:
    client_mod, _error_mod, _event_mod = _import_wyoming()
    client = client_mod.AsyncClient.from_uri(tcp_uri(endpoint))
    if getattr(client, "read_timeout", None) is not None:
        client.read_timeout = None
    try:
        await asyncio.wait_for(client.connect(), connect_timeout)
    except asyncio.TimeoutError as exc:
        raise BridgeError(connect_failed("server", endpoint.label)) from exc
    except OSError as exc:
        raise BridgeError(connect_failed("server", endpoint.label)) from exc
    if getattr(client, "read_timeout", None) is not None:
        client.read_timeout = None
    return client


async def _close(client: Any) -> None:
    try:
        await asyncio.wait_for(client.disconnect(), 2)
    except Exception:
        writer = getattr(client, "_writer", None)
        if writer is not None:
            writer.close()


class _LineRejected(Exception):
    """Raised before the wyoming library parses a line that is not a JSON object."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class _JsonLineProbe:
    """Stop a bad line before wyoming.event.async_read_event parses it."""

    def __init__(self, reader: Any) -> None:
        self._reader = reader

    async def readline(self) -> bytes:
        line = await self._reader.readline()
        if not line:
            return line
        try:
            parsed = json.loads(line)
        except (UnicodeError, json.JSONDecodeError, ValueError):
            raise _LineRejected("json") from None
        if not isinstance(parsed, dict):
            raise _LineRejected("object")
        return line

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)


def _probe_reader(client: Any) -> _JsonLineProbe | None:
    reader = getattr(client, "_reader", None)
    if reader is None:
        return None
    if isinstance(reader, _JsonLineProbe):
        return reader
    probe = _JsonLineProbe(reader)
    client._reader = probe
    return probe


async def _read(client: Any, kind: str) -> Any:
    _client_mod, error_mod, _event_mod = _import_wyoming()
    _probe_reader(client)
    try:
        event = await client.read_event()
    except _LineRejected as exc:
        if exc.kind == "object":
            raise BridgeError(not_an_object(kind), maybe_started=True) from exc
        raise BridgeError(unreadable_line(kind), maybe_started=True) from exc
    except asyncio.TimeoutError as exc:
        raise BridgeError(disconnected(kind), maybe_started=True) from exc
    except OSError as exc:
        raise BridgeError(disconnected(kind), maybe_started=True) from exc
    if event is None:
        raise BridgeError(disconnected(kind), maybe_started=True)
    _log_event(event)
    if error_mod.Error.is_type(event.type):
        code = ""
        data = event.data if isinstance(event.data, dict) else {}
        raw = data.get("code")
        if isinstance(raw, str):
            code = raw[:80]
        raise BridgeError(server_error(kind, code), maybe_started=True)
    return event


async def _exchange(
    endpoint: Endpoint,
    kind: str,
    budget: float,
    timeout_message: str,
    body: Callable[[Any], Awaitable[Any]],
    *,
    connect_timeout: float = CONNECT_TIMEOUT_S,
    maybe_started: bool = False,
) -> Any:
    try:
        client = await _open(endpoint, connect_timeout)
    except BridgeError:
        raise
    except Exception as exc:
        raise BridgeError(connect_failed(kind, endpoint.label)) from exc
    try:
        try:
            return await asyncio.wait_for(body(client), budget)
        except BridgeError:
            raise
        except asyncio.TimeoutError as exc:
            raise BridgeError(timeout_message, maybe_started=maybe_started) from exc
    finally:
        await _close(client)


def _languages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _installed(value: Any) -> bool:
    if value is None:
        return True
    return bool(value)


def summarize_info(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise BridgeError(unexpected_event("describe", "info"))
    asr: list[dict[str, Any]] = []
    tts: list[dict[str, Any]] = []
    programs = data.get("asr") or []
    if not isinstance(programs, list):
        programs = []
    for program in programs:
        if not isinstance(program, dict):
            continue
        program_name = program.get("name") if isinstance(program.get("name"), str) else ""
        models = program.get("models") or []
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict) or not isinstance(model.get("name"), str):
                continue
            asr.append({
                "program": program_name,
                "name": model["name"],
                "languages": _languages(model.get("languages")),
                "installed": _installed(model.get("installed")),
            })
    tts_programs = data.get("tts") or []
    if not isinstance(tts_programs, list):
        tts_programs = []
    for program in tts_programs:
        if not isinstance(program, dict):
            continue
        program_name = program.get("name") if isinstance(program.get("name"), str) else ""
        voices = program.get("voices") or []
        if not isinstance(voices, list):
            continue
        for voice in voices:
            if not isinstance(voice, dict) or not isinstance(voice.get("name"), str):
                continue
            speakers = []
            raw_speakers = voice.get("speakers") or []
            if isinstance(raw_speakers, list):
                for speaker in raw_speakers:
                    if isinstance(speaker, dict) and isinstance(speaker.get("name"), str):
                        speakers.append(speaker["name"])
                    elif isinstance(speaker, str):
                        speakers.append(speaker)
            tts.append({
                "program": program_name,
                "name": voice["name"],
                "languages": _languages(voice.get("languages")),
                "speakers": speakers,
                "installed": _installed(voice.get("installed")),
            })
    if len(asr) > MAX_CATALOG or len(tts) > MAX_CATALOG:
        raise BridgeError(catalog_too_large())
    return {"asr": asr, "tts": tts}


async def describe(
    endpoint: Endpoint,
    *,
    budget: float = DESCRIBE_TIMEOUT_S,
    connect_timeout: float = CONNECT_TIMEOUT_S,
) -> dict[str, Any]:
    async def body(client: Any) -> dict[str, Any]:
        _client_mod, _error_mod, _event_mod = _import_wyoming()
        from wyoming.info import Describe

        await client.write_event(Describe().event())
        event = await _read(client, "describe")
        if event.type != "info":
            raise BridgeError(unexpected_event("describe", str(event.type)))
        return summarize_info(event.data)

    try:
        return await _exchange(
            endpoint, "describe", budget, describe_timeout(endpoint.label), body,
            connect_timeout=connect_timeout,
        )
    except BridgeError as exc:
        if exc.maybe_started and exc.message == disconnected("describe"):
            raise BridgeError(disconnected("describe")) from exc
        raise


async def transcribe_wav(
    endpoint: Endpoint,
    wav_path: str,
    *,
    model: str | None = None,
    language: str | None = None,
    budget: float = STT_TIMEOUT_S,
    connect_timeout: float = CONNECT_TIMEOUT_S,
) -> str:
    async def body(client: Any) -> str:
        import wave

        from wyoming.asr import Transcribe
        from wyoming.audio import wav_to_chunks

        kwargs: dict[str, Any] = {}
        if model:
            kwargs["name"] = model
        if language:
            kwargs["language"] = language
        await client.write_event(Transcribe(**kwargs).event())
        with wave.open(wav_path, "rb") as wav_file:
            for chunk in wav_to_chunks(wav_file, samples_per_chunk=1024, start_event=True, stop_event=True):
                await client.write_event(chunk.event())
        while True:
            event = await _read(client, "speech recognition")
            if event.type == "transcript":
                data = event.data if isinstance(event.data, dict) else {}
                text = data.get("text")
                if not isinstance(text, str):
                    raise BridgeError(unexpected_event("speech recognition", "transcript"), maybe_started=True)
                return text
            if event.type in {"transcript-start", "transcript-chunk", "transcript-stop"}:
                continue
            raise BridgeError(unexpected_event("speech recognition", str(event.type)), maybe_started=True)

    return await _exchange(
        endpoint,
        "speech recognition",
        budget,
        speech_timeout("speech recognition", endpoint.label, int(budget)),
        body,
        connect_timeout=connect_timeout,
        maybe_started=True,
    )


async def synthesize_pcm(
    endpoint: Endpoint,
    text: str,
    *,
    voice: str | None = None,
    speaker: str | None = None,
    budget: float = TTS_TIMEOUT_S,
    connect_timeout: float = CONNECT_TIMEOUT_S,
) -> tuple[int, int, int, bytes]:
    async def body(client: Any) -> tuple[int, int, int, bytes]:
        from wyoming.tts import Synthesize, SynthesizeVoice

        voice_obj = None
        if voice or speaker:
            voice_obj = SynthesizeVoice(name=voice, speaker=speaker)
        await client.write_event(Synthesize(text, voice=voice_obj).event())
        rate = width = channels = None
        parts: list[bytes] = []
        total = 0
        while True:
            event = await _read(client, "speech synthesis")
            data = event.data if isinstance(event.data, dict) else {}
            if event.type == "audio-start":
                rate = data.get("rate")
                width = data.get("width")
                channels = data.get("channels")
                continue
            if event.type == "audio-chunk":
                payload = event.payload if isinstance(event.payload, (bytes, bytearray)) else b""
                total += len(payload)
                if total > MAX_PCM_BYTES:
                    raise BridgeError(pcm_too_large(), maybe_started=True)
                parts.append(bytes(payload))
                continue
            if event.type == "audio-stop":
                break
            raise BridgeError(unexpected_event("speech synthesis", str(event.type)), maybe_started=True)
        audio = b"".join(parts)
        if not audio:
            raise BridgeError(empty_audio(), maybe_started=True)
        if rate is None or not isinstance(rate, int) or not isinstance(width, int) or not isinstance(channels, int):
            raise BridgeError(bad_audio_format(), maybe_started=True)
        if width != 2 or channels < 1 or rate < 1:
            raise BridgeError(bad_audio_format(), maybe_started=True)
        return rate, width, channels, audio

    return await _exchange(
        endpoint,
        "speech synthesis",
        budget,
        speech_timeout("speech synthesis", endpoint.label, int(budget)),
        body,
        connect_timeout=connect_timeout,
        maybe_started=True,
    )


def run_async(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Run one coroutine factory from sync code, including inside a running loop."""
    def runner() -> Any:
        return asyncio.run(fn(*args, **kwargs))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return runner()
    box: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def worker() -> None:
        try:
            box["value"] = runner()
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            error["value"] = exc

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    if error:
        raise error["value"]
    return box.get("value")


def describe_sync(endpoint: Endpoint, **kwargs: Any) -> dict[str, Any]:
    return run_async(describe, endpoint, **kwargs)


def transcribe_sync(endpoint: Endpoint, wav_path: str, **kwargs: Any) -> str:
    return run_async(transcribe_wav, endpoint, wav_path, **kwargs)


def synthesize_sync(endpoint: Endpoint, text: str, **kwargs: Any) -> tuple[int, int, int, bytes]:
    return run_async(synthesize_pcm, endpoint, text, **kwargs)
