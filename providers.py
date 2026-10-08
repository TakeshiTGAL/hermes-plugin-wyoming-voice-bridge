"""Hermes STT and TTS providers. Imported only after the register methods exist."""
from __future__ import annotations

import os
from typing import Any

if __package__:
    from .service import configured, synthesize_to, transcribe_file
else:
    from service import configured, synthesize_to, transcribe_file


# read_raw_config failed, or the stt value was not a mapping.
RAW_UNREADABLE = object()


def _usable(value: object) -> str | None:
    """Skip empty and the word default. Other spellings, including en, stay."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text == "" or text == "default":
        return None
    return text


def _first_nonempty(*values: object) -> str | None:
    """Hermes's own resolution keeps any non-empty string, including default."""
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _read_raw_stt() -> dict | object:
    try:
        from hermes_cli.config import read_raw_config
        raw = read_raw_config()
    except Exception:
        return RAW_UNREADABLE
    if not isinstance(raw, dict):
        return RAW_UNREADABLE
    stt = raw.get("stt")
    if stt is None:
        return {}
    if not isinstance(stt, dict):
        return RAW_UNREADABLE
    return stt


def _loaded_resolution() -> str | None:
    """Language Hermes would pass when no pre_transcription hook set one.

    That value includes the en Hermes fills in for stt.language.
    """
    try:
        from hermes_cli.config import load_config
        cfg = load_config()
    except Exception:
        cfg = {}
    stt = cfg.get("stt") if isinstance(cfg, dict) else None
    if not isinstance(stt, dict):
        stt = {}
    section = stt.get("wyoming")
    section_language = section.get("language") if isinstance(section, dict) else None
    return _first_nonempty(
        section_language,
        stt.get("language"),
        os.environ.get("HERMES_LOCAL_STT_LANGUAGE"),
    )


def _written(mapping: dict, key: str) -> str | None:
    if key not in mapping:
        return None
    return _usable(mapping.get(key))


def choose_request_language(
    passed: str | None,
    *,
    wyoming_env: str | None,
    local_env: str | None,
    raw_stt: dict | object,
    loaded_resolution: str | None,
) -> str | None:
    """One language, or none.

    Order: hook, stt.wyoming.language, WYOMING_STT_LANGUAGE, raw stt.language,
    HERMES_LOCAL_STT_LANGUAGE. Raw stt.language counts whether the user or
    Hermes wrote it. A missing config skips the section and that key.
    Hermes already ran pre_transcription. This plugin does not call it again.
    A passed value that differs from Hermes's own resolution is that hook.
    The same string is not treated as a hook, including when both are en.
    """
    passed_text = passed.strip() if isinstance(passed, str) else ""
    resolved_text = loaded_resolution.strip() if isinstance(loaded_resolution, str) else ""
    if passed_text and passed_text != resolved_text:
        hook = _usable(passed)
        if hook:
            return hook
    readable = raw_stt is not RAW_UNREADABLE and isinstance(raw_stt, dict)
    if readable:
        section = raw_stt.get("wyoming")
        if isinstance(section, dict):
            chosen = _written(section, "language")
            if chosen:
                return chosen
    chosen = _usable(wyoming_env)
    if chosen:
        return chosen
    if readable:
        chosen = _written(raw_stt, "language")
        if chosen:
            return chosen
    return _usable(local_env)


def resolve_request_language(passed: str | None) -> str | None:
    return choose_request_language(
        passed,
        wyoming_env=os.environ.get("WYOMING_STT_LANGUAGE"),
        local_env=os.environ.get("HERMES_LOCAL_STT_LANGUAGE"),
        raw_stt=_read_raw_stt(),
        loaded_resolution=_loaded_resolution(),
    )


def _library_imports() -> bool:
    try:
        import wyoming  # noqa: F401
    except Exception:
        return False
    return True


def build_providers() -> tuple[Any, Any]:
    from agent.transcription_provider import TranscriptionProvider
    from agent.tts_provider import TTSProvider

    class WyomingTranscription(TranscriptionProvider):
        @property
        def name(self) -> str:
            return "wyoming"

        @property
        def display_name(self) -> str:
            return "Wyoming"

        def is_available(self) -> bool:
            return _library_imports() and configured("WYOMING_STT")

        def list_models(self) -> list[dict[str, Any]]:
            if not self.is_available():
                return []
            chosen = (os.environ.get("WYOMING_STT_MODEL") or "default").strip() or "default"
            return [{
                "id": chosen,
                "display": "Wyoming server. Not a live catalog; call wyoming_voice_status.",
            }]

        def get_setup_schema(self) -> dict[str, Any]:
            return {
                "name": "Wyoming",
                "badge": "local",
                "tag": "Speech recognition on a Wyoming server you run",
                "env_vars": [
                    {"key": "WYOMING_STT_HOST", "prompt": "Wyoming STT host", "url": ""},
                    {"key": "WYOMING_STT_PORT", "prompt": "Wyoming STT port", "url": ""},
                ],
            }

        def transcribe(self, file_path: str, *, model: str | None = None, language: str | None = None, **extra: Any) -> dict[str, Any]:
            del extra
            chosen = resolve_request_language(language)
            return transcribe_file(
                file_path,
                model=model,
                language=chosen,
                env_model=os.environ.get("WYOMING_STT_MODEL"),
                env_language=None,
            )

    class WyomingSpeech(TTSProvider):
        voice_compatible = True

        @property
        def name(self) -> str:
            return "wyoming"

        @property
        def display_name(self) -> str:
            return "Wyoming"

        def is_available(self) -> bool:
            return _library_imports() and configured("WYOMING_TTS")

        def list_models(self) -> list[dict[str, Any]]:
            if not self.is_available():
                return []
            return [{"id": "default", "display": "Wyoming server. Not a live catalog; call wyoming_voice_status."}]

        def list_voices(self) -> list[dict[str, Any]]:
            if not self.is_available():
                return []
            chosen = (os.environ.get("WYOMING_TTS_VOICE") or "default").strip() or "default"
            return [{"id": chosen, "display": "Wyoming voice. Not a live catalog; call wyoming_voice_status."}]

        def get_setup_schema(self) -> dict[str, Any]:
            return {
                "name": "Wyoming",
                "badge": "local",
                "tag": "Speech synthesis on a Wyoming server you run",
                "env_vars": [
                    {"key": "WYOMING_TTS_HOST", "prompt": "Wyoming TTS host", "url": ""},
                    {"key": "WYOMING_TTS_PORT", "prompt": "Wyoming TTS port", "url": ""},
                ],
            }

        def synthesize(
            self,
            text: str,
            output_path: str,
            *,
            voice: str | None = None,
            model: str | None = None,
            speed: float | None = None,
            format: str = "mp3",
            **extra: Any,
        ) -> str:
            del model, speed, format, extra
            return synthesize_to(
                text,
                output_path,
                voice=voice,
                env_voice=os.environ.get("WYOMING_TTS_VOICE"),
            )

    return WyomingTranscription(), WyomingSpeech()
