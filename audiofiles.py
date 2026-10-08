"""WAV in, WAV out. Audio bytes are not logged."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any

if __package__:
    from .messages import (
        FFMPEG_MAX_SECONDS,
        FFMPEG_TIMEOUT_S,
        MAX_AUDIO_BYTES,
        MAX_PCM_BYTES,
        audio_too_large,
        ffmpeg_failed,
        ffmpeg_missing,
        input_pcm_too_large,
        no_parent,
        not_wav,
        output_exists,
        symlink_refused,
        temp_exists,
        write_refused,
    )
    from .session import BridgeError
else:
    from messages import (
        FFMPEG_MAX_SECONDS,
        FFMPEG_TIMEOUT_S,
        MAX_AUDIO_BYTES,
        MAX_PCM_BYTES,
        audio_too_large,
        ffmpeg_failed,
        ffmpeg_missing,
        input_pcm_too_large,
        no_parent,
        not_wav,
        output_exists,
        symlink_refused,
        temp_exists,
        write_refused,
    )
    from session import BridgeError


def _refuse_symlink(path: Path, what: str) -> None:
    if path.is_symlink():
        raise BridgeError(symlink_refused(what))


def _pcm_nbytes(path: Path) -> int:
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() * wav_file.getsampwidth() * wav_file.getnchannels()


def _reject_oversized_pcm(path: Path, temp_dir: str | None) -> None:
    try:
        size = _pcm_nbytes(path)
    except (wave.Error, EOFError, OSError) as exc:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise BridgeError(not_wav()) from exc
    if size > MAX_PCM_BYTES:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise BridgeError(input_pcm_too_large())


def load_pcm_wav(path: str) -> str:
    """Return a 16 kHz mono 16-bit WAV path. Caller deletes the temp dir when it is not `path`."""
    audio = Path(path)
    _refuse_symlink(audio, "recording")
    if not audio.is_file():
        raise BridgeError("The audio file was not found. Nothing was sent.")
    if audio.stat().st_size > MAX_AUDIO_BYTES:
        raise BridgeError(audio_too_large())
    if audio.suffix.lower() == ".wav" and _already_target(audio):
        _reject_oversized_pcm(audio, None)
        return str(audio)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise BridgeError(ffmpeg_missing(audio.suffix.lower()))
    temp_dir = tempfile.mkdtemp(prefix="wyoming-voice-")
    dest = os.path.join(temp_dir, "speech.wav")
    try:
        subprocess.run(
            [
                ffmpeg, "-y", "-t", str(FFMPEG_MAX_SECONDS), "-i", str(audio),
                "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", dest,
            ],
            check=True,
            timeout=FFMPEG_TIMEOUT_S,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise BridgeError(ffmpeg_failed()) from exc
    if not _already_target(Path(dest)):
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise BridgeError(not_wav())
    _reject_oversized_pcm(Path(dest), temp_dir)
    return dest


def _already_target(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wav_file:
            return (
                wav_file.getframerate() == 16000
                and wav_file.getsampwidth() == 2
                and wav_file.getnchannels() == 1
                and wav_file.getnframes() > 0
            )
    except (wave.Error, EOFError, OSError):
        return False


def _import_write_checks() -> tuple[Any, Any]:
    import agent.file_safety as safety

    denied = getattr(safety, "is_write_denied", None)
    approval = getattr(safety, "is_write_approval_required", None)
    if not callable(denied) or not callable(approval):
        raise AttributeError("agent.file_safety write check was renamed")
    return denied, approval


def _write_guard(path: str, loader: Any = None) -> None:
    load = _import_write_checks if loader is None else loader
    try:
        denied_fn, approval_fn = load()
    except Exception as exc:
        raise BridgeError(write_refused()) from exc
    if not callable(denied_fn) or not callable(approval_fn):
        raise BridgeError(write_refused())
    try:
        denied = denied_fn(path) or approval_fn(path)
    except Exception as exc:
        raise BridgeError(write_refused()) from exc
    if denied:
        raise BridgeError(write_refused())


def write_wav(
    output_path: str,
    rate: int,
    width: int,
    channels: int,
    pcm: bytes,
    *,
    guard: Any = None,
) -> str:
    destination = Path(output_path)
    if destination.suffix.lower() != ".wav":
        destination = destination.with_suffix(".wav")
    _refuse_symlink(Path(output_path), "output file")
    if destination != Path(output_path):
        _refuse_symlink(destination, "output file")
    if not destination.parent.is_dir():
        raise BridgeError(no_parent())
    if destination.exists():
        raise BridgeError(output_exists())
    check = _write_guard if guard is None else guard
    check(str(destination))
    temp_path = destination.with_name(f".{destination.name}.wyoming-tmp")
    if temp_path.exists():
        raise BridgeError(temp_exists())
    check(str(temp_path))
    try:
        with wave.open(str(temp_path), "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(width)
            wav_file.setframerate(rate)
            wav_file.writeframes(pcm)
        os.replace(temp_path, destination)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return str(destination)
