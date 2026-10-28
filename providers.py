"""Hermes STT and TTS providers. Imported only after the register methods exist."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

if __package__:
    from .endpoints import setting
    from .service import configured, synthesize_to, transcribe_file
else:
    from endpoints import setting
    from service import configured, synthesize_to, transcribe_file


def _usable(value: object) -> str | None:
    """Skip empty and the word default. Other spellings, including en, stay."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text == "" or text.lower() == "default":
        return None
    return text


def language_from_config(value: object) -> str | None:
    """The plugin setting only. Empty and the word default send no language."""
    return _usable(value)


def read_plugin_language(read: Callable[[], object] | None) -> str | None:
    """Call the register-time reader. A missing reader or a raised read sends nothing."""
    if not callable(read):
        return None
    try:
        value = read()
    except Exception:
        return None
    return language_from_config(value)


def _library_imports() -> bool:
    if __package__:
        from .wyoming_pin import library_status
    else:
        from wyoming_pin import library_status
    if library_status() != "ready":
        return False
    try:
        import wyoming  # noqa: F401
    except Exception:
        return False
    return True


def build_providers(read_language: Callable[[], object] | None = None) -> tuple[Any, Any]:
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
            chosen = (setting("WYOMING_STT_MODEL") or "default").strip() or "default"
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
            del extra, language
            chosen = read_plugin_language(read_language)
            return transcribe_file(
                file_path,
                model=model,
                language=chosen,
                env_model=setting("WYOMING_STT_MODEL"),
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
            chosen = (setting("WYOMING_TTS_VOICE") or "default").strip() or "default"
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
                env_voice=setting("WYOMING_TTS_VOICE"),
            )

    return WyomingTranscription(), WyomingSpeech()
