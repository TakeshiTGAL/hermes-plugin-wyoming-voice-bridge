"""Speech and describe, without importing Hermes."""
from __future__ import annotations

import os
import shutil
from typing import Any, Callable

if __package__:
    from .audiofiles import load_pcm_wav, write_wav
    from .endpoints import Endpoint, EndpointError, endpoint_from_env
    from .gate import approve_describe
    from .messages import (
        NAME_MAX,
        bad_endpoint,
        bad_name,
        language_needs_model,
        language_refused,
        library_missing,
        name_refused,
        no_installed,
        not_configured,
        text_too_long,
        which_refused,
        MAX_TEXT_CHARS,
    )
    from .session import BridgeError, describe_sync, synthesize_sync, transcribe_sync
else:
    from audiofiles import load_pcm_wav, write_wav
    from endpoints import Endpoint, EndpointError, endpoint_from_env
    from gate import approve_describe
    from messages import (
        NAME_MAX,
        bad_endpoint,
        bad_name,
        language_needs_model,
        language_refused,
        library_missing,
        name_refused,
        no_installed,
        not_configured,
        text_too_long,
        which_refused,
        MAX_TEXT_CHARS,
    )
    from session import BridgeError, describe_sync, synthesize_sync, transcribe_sync

DescribeFn = Callable[..., dict[str, Any]]
TranscribeFn = Callable[..., str]
SynthesizeFn = Callable[..., tuple[int, int, int, bytes]]


def _env_endpoint(prefix: str) -> Endpoint | None:
    try:
        return endpoint_from_env(prefix)
    except EndpointError as exc:
        kind = "speech recognition" if prefix.endswith("STT") else "speech synthesis"
        raise BridgeError(bad_endpoint(kind, str(exc))) from exc


def _check_name(kind: str, name: str | None) -> str | None:
    if name is None:
        return None
    text = name.strip()
    if text == "" or text == "default":
        return None
    if len(text) > NAME_MAX or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise BridgeError(bad_name(kind))
    return text


def _language_key(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def _listed_language(wanted: str, available: list[str]) -> str | None:
    """Return the server's own spelling, or None. `en` does not match `en-US`."""
    needle = _language_key(wanted)
    if not needle:
        return None
    for item in available:
        if isinstance(item, str) and _language_key(item) == needle:
            return item
    return None


def _row_installed(row: dict[str, Any]) -> bool:
    """A missing or null `installed` field means the server listed it as installed."""
    if "installed" not in row or row.get("installed") is None:
        return True
    return bool(row.get("installed"))


def _installed(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if _row_installed(row)]


def _require_asr(
    summary: dict[str, Any], model: str | None, language: str | None,
) -> tuple[str | None, str | None]:
    rows = _installed(summary.get("asr") or [])
    if not rows:
        raise BridgeError(no_installed("speech-recognition model"))
    chosen = model
    if chosen:
        match = [row for row in rows if row.get("name") == chosen]
        if not match:
            raise BridgeError(name_refused("Model", chosen))
        rows = match
    sent_language = None
    if language:
        spellings = [
            _listed_language(language, row.get("languages") or [])
            for row in rows
        ]
        if chosen or len(rows) == 1:
            sent_language = next((item for item in spellings if item), None)
            if sent_language is None:
                raise BridgeError(language_refused(language))
        elif all(spellings):
            sent_language = spellings[0]
        elif any(spellings):
            raise BridgeError(language_needs_model(language))
        else:
            raise BridgeError(language_refused(language))
    return chosen, sent_language


def _require_voice(summary: dict[str, Any], voice: str | None) -> tuple[str | None, str | None]:
    rows = _installed(summary.get("tts") or [])
    if not rows:
        raise BridgeError(no_installed("voice"))
    if not voice:
        return None, None
    for row in rows:
        if row.get("name") == voice:
            return voice, None
        if voice in (row.get("speakers") or []):
            return row.get("name"), voice
    raise BridgeError(name_refused("Voice", voice))


def _library_ready() -> None:
    try:
        import wyoming  # noqa: F401
    except Exception as exc:
        raise BridgeError(library_missing()) from exc


def transcribe_file(
    path: str,
    *,
    model: str | None = None,
    language: str | None = None,
    env_model: str | None = None,
    env_language: str | None = None,
    describe_fn: DescribeFn = describe_sync,
    transcribe_fn: TranscribeFn = transcribe_sync,
) -> dict[str, Any]:
    try:
        _library_ready()
        endpoint = _env_endpoint("WYOMING_STT")
        if endpoint is None:
            raise BridgeError(not_configured("speech recognition"))
        chosen_model = _check_name("Model", model if model not in (None, "") else env_model)
        chosen_language = _check_name("Language", language if language not in (None, "") else env_language)
        wav_path = load_pcm_wav(path)
        cleanup = None if wav_path == path else os.path.dirname(wav_path)
        try:
            summary = describe_fn(endpoint)
            sent_model, sent_language = _require_asr(summary, chosen_model, chosen_language)
            text = transcribe_fn(endpoint, wav_path, model=sent_model, language=sent_language)
        finally:
            if cleanup:
                shutil.rmtree(cleanup, ignore_errors=True)
        return {"success": True, "transcript": text, "provider": "wyoming"}
    except BridgeError as exc:
        return {"success": False, "transcript": "", "provider": "wyoming", "error": exc.message}


def synthesize_to(
    text: str,
    output_path: str,
    *,
    voice: str | None = None,
    env_voice: str | None = None,
    describe_fn: DescribeFn = describe_sync,
    synthesize_fn: SynthesizeFn = synthesize_sync,
    writer: Callable[..., str] = write_wav,
) -> str:
    _library_ready()
    endpoint = _env_endpoint("WYOMING_TTS")
    if endpoint is None:
        raise BridgeError(not_configured("speech synthesis"))
    spoken = text if isinstance(text, str) else ""
    if not spoken.strip():
        raise BridgeError("There is no text to speak. Nothing was sent.")
    if len(spoken) > MAX_TEXT_CHARS:
        raise BridgeError(text_too_long())
    chosen = _check_name("Voice", voice if voice not in (None, "") else env_voice)
    summary = describe_fn(endpoint)
    voice_name, speaker = _require_voice(summary, chosen)
    rate, width, channels, pcm = synthesize_fn(
        endpoint, spoken, voice=voice_name, speaker=speaker,
    )
    return writer(output_path, rate, width, channels, pcm)


def _public_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    public = []
    for row in rows:
        item = {
            "name": row.get("name"),
            "languages": (row.get("languages") or [])[:200],
            "installed": _row_installed(row),
            "program": row.get("program") or "",
        }
        if len(row.get("languages") or []) > 200:
            item["languages_truncated"] = True
        if "speakers" in row:
            speakers = row.get("speakers") or []
            item["speakers"] = speakers[:50]
            if len(speakers) > 50:
                item["speakers_truncated"] = True
        public.append(item)
    return public


def _one_status(kind: str, prefix: str, describe_fn: DescribeFn) -> dict[str, Any]:
    try:
        endpoint = _env_endpoint(prefix)
    except BridgeError as exc:
        return {"success": False, "error": exc.message}
    if endpoint is None:
        return {"success": False, "error": not_configured(kind)}
    try:
        summary = describe_fn(endpoint)
    except BridgeError as exc:
        return {"success": False, "error": exc.message, "host": endpoint.host, "port": endpoint.port}
    key = "asr" if prefix.endswith("STT") else "tts"
    rows = summary.get(key) or []
    installed = [row for row in rows if _row_installed(row)]
    return {
        "success": True,
        "host": endpoint.host,
        "port": endpoint.port,
        "ready": bool(installed),
        "warning": None if installed else no_installed("model" if key == "asr" else "voice"),
        "models": _public_rows(rows),
    }


def status(which: str, *, describe_fn: DescribeFn = describe_sync, approver: Callable[[list[str]], str | None] = approve_describe) -> dict[str, Any]:
    if which not in {"stt", "tts", "both"}:
        return {"success": False, "error": which_refused()}
    try:
        _library_ready()
    except BridgeError as exc:
        return {"success": False, "error": exc.message}
    sides = []
    if which in {"stt", "both"}:
        sides.append(("speech recognition", "WYOMING_STT"))
    if which in {"tts", "both"}:
        sides.append(("speech synthesis", "WYOMING_TTS"))
    targets = []
    for kind, prefix in sides:
        try:
            endpoint = _env_endpoint(prefix)
        except BridgeError as exc:
            return {"success": False, "error": exc.message}
        if endpoint is None:
            return {"success": False, "error": not_configured(kind)}
        targets.append(endpoint.label)
    denied = approver(targets)
    if denied:
        return {"success": False, "error": denied}
    parts = {}
    if which in {"stt", "both"}:
        parts["stt"] = _one_status("speech recognition", "WYOMING_STT", describe_fn)
    if which in {"tts", "both"}:
        parts["tts"] = _one_status("speech synthesis", "WYOMING_TTS", describe_fn)
    ok = all(part.get("success") for part in parts.values())
    body: dict[str, Any] = {"success": ok}
    body.update(parts)
    return body


def configured(prefix: str) -> bool:
    try:
        return endpoint_from_env(prefix) is not None
    except EndpointError:
        return False
