"""English sentences the user sees. Tests compare these strings."""
from __future__ import annotations

CONNECT_TIMEOUT_S = 5
DESCRIBE_TIMEOUT_S = 10
TTS_TIMEOUT_S = 60
STT_TIMEOUT_S = 120
FFMPEG_TIMEOUT_S = 30
MAX_TEXT_CHARS = 4000
# Decimal megabytes. The acceptance table contrasts this 25 MB cap with the 20 MiB PCM cap.
MAX_AUDIO_BYTES = 25 * 1000 * 1000
MAX_PCM_BYTES = 20 * 1024 * 1024
# 16 kHz, 16-bit, mono is 32000 bytes/s. One second past the PCM cap, so
# ffmpeg stops and the size check still refuses a file that would have been longer.
FFMPEG_MAX_SECONDS = (MAX_PCM_BYTES // 32000) + 1
MAX_CATALOG = 500
APPROVAL_TEXT_MAX = 500
NAME_MAX = 128


def not_configured(kind: str) -> str:
    return f"Wyoming {kind} host and port are not set."


def bad_endpoint(kind: str, detail: str) -> str:
    return f"Wyoming {kind} address was refused before connecting. {detail}"


def connect_failed(kind: str, endpoint: str) -> str:
    return (
        f"Could not connect to Wyoming {kind} at {endpoint} "
        f"within {CONNECT_TIMEOUT_S}s. Nothing was retried."
    )


def describe_timeout(endpoint: str) -> str:
    return (
        f"Timed out after {DESCRIBE_TIMEOUT_S}s waiting for a describe reply from {endpoint}. "
        "The server may already be working. It was not sent again. "
        "Check the server before you try again."
    )


def speech_timeout(kind: str, endpoint: str, seconds: int) -> str:
    action = "transcribing this audio" if kind == "speech recognition" else "synthesizing this text"
    return (
        f"Timed out after {seconds}s talking to Wyoming {kind} at {endpoint}. "
        f"The server may already be {action}. It was not sent again. "
        "Check the server before you try again."
    )


def disconnected(kind: str) -> str:
    return (
        f"The Wyoming {kind} server closed the connection before a finished reply. "
        "Nothing was kept and nothing was retried."
    )


def unreadable_line(kind: str) -> str:
    return (
        f"The Wyoming {kind} server sent a line that is not JSON. "
        "Nothing was kept and nothing was retried."
    )


def not_an_object(kind: str) -> str:
    return (
        f"The Wyoming {kind} server sent JSON that is not an object. "
        "Nothing was kept and nothing was retried."
    )


def server_error(kind: str, code: str) -> str:
    shown = code if code else "unspecified"
    return f"The Wyoming {kind} server returned an error ({shown}). Nothing was retried."


def unexpected_event(kind: str, event_type: str) -> str:
    return f"The Wyoming {kind} server sent an unexpected event ({event_type})."


def no_installed(kind: str) -> str:
    return (
        f"This Wyoming server listed no installed {kind}. "
        "Nothing else was sent."
    )


def _copy_spelling() -> str:
    return "Names are case-sensitive. Copy the spelling with wyoming_voice_status."


def name_refused(kind: str, name: str) -> str:
    return (
        f"{kind} {name!r} is not in the server's installed list. "
        "Nothing else was sent. "
        + _copy_spelling()
    )


def language_refused(language: str) -> str:
    return (
        f"Language {language!r} is not in the server's installed list. "
        "No audio was sent. "
        + _copy_spelling()
    )


def language_needs_model(language: str) -> str:
    return (
        f"Language {language!r} is not listed for every installed model, "
        "and no model was named. Name a model and try again. No audio was sent. "
        + _copy_spelling()
    )


def empty_audio() -> str:
    return "The server finished and sent no audio. The file was not kept."


def text_too_long() -> str:
    return (
        f"Text longer than {MAX_TEXT_CHARS} characters was not sent. "
        "Shorten it and try again."
    )


def audio_too_large() -> str:
    return "Audio larger than 25 MB was not sent."


def pcm_too_large() -> str:
    return "The server sent more than 20 MiB of audio. The file was not written."


def input_pcm_too_large() -> str:
    return (
        "This audio expands past 20 MiB of 16 kHz, 16-bit, mono PCM, so it was not sent."
    )


def catalog_too_large() -> str:
    return "The server listed more than 500 models or voices. Nothing else was sent."


def bad_name(kind: str) -> str:
    return f"{kind} contains a control character or is longer than {NAME_MAX} characters. It was not sent."


def ffmpeg_missing(suffix: str) -> str:
    return (
        f"This audio is {suffix or 'an unknown type'}, and ffmpeg is not installed, "
        "so it was not sent. WAV at 16 kHz, 16-bit, mono does not need ffmpeg."
    )


def ffmpeg_failed() -> str:
    return "ffmpeg could not convert this audio to 16 kHz mono WAV. It was not sent."


def not_wav() -> str:
    return "The converted audio was not a readable WAV file. It was not sent."


def symlink_refused(what: str) -> str:
    return f"Refusing a symbolic link for the {what}."


def write_refused() -> str:
    return "Refusing to write the speech file. The write guard blocked that path, or the guard could not be loaded."


def no_parent() -> str:
    return "The output directory does not exist. The speech file was not written."


def output_exists() -> str:
    return (
        "That speech file already exists. This plugin did not write over it. "
        "When the path Hermes asked for is that file, Hermes's speech tool deletes it "
        "while cleaning up the failed call."
    )


def temp_exists() -> str:
    return "The temporary file for that speech already exists. This plugin did not replace it."


def library_missing() -> str:
    return "The wyoming library is not installed, so nothing was sent."


def approval_blocked(reason: str) -> str:
    return reason


def approval_too_long() -> str:
    return "The approval question does not fit in one message, so nothing was sent."


def not_approved() -> str:
    return "The describe was not approved, so nothing was sent."


def host_process_blocked() -> str:
    return (
        "BLOCKED: this process is the plugin host, so the approval check would not be the parent's. "
        "Nothing was sent."
    )


def which_refused() -> str:
    return "which must be stt, tts, or both. Nothing was sent."


def bad_audio_format() -> str:
    return "The server's audio format was not 16-bit PCM. The file was not written."
