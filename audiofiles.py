"""WAV in, WAV out. Audio bytes are not logged."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
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
        ffmpeg_unpinned,
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
        ffmpeg_unpinned,
        input_pcm_too_large,
        no_parent,
        not_wav,
        output_exists,
        symlink_refused,
        temp_exists,
        write_refused,
    )
    from session import BridgeError


# sha256 hex of ffmpeg binaries this build may run, keyed by (sys.platform, platform.machine()).
# Empty until an audited pin exists. A path whose digest is not listed is not started.
FFMPEG_SHA256: dict[tuple[str, str], frozenset[str]] = {}


def _ffmpeg_digest(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def approved_ffmpeg() -> str | None:
    """Real path of ffmpeg when its sha256 is listed for this OS and CPU. Otherwise None."""
    found = shutil.which("ffmpeg")
    if not found or os.path.islink(found):
        return None
    real = os.path.realpath(found)
    if not os.path.isfile(real):
        return None
    try:
        digest = _ffmpeg_digest(real)
    except OSError:
        return None
    allowed = FFMPEG_SHA256.get((sys.platform, platform.machine()))
    if not allowed or digest not in allowed:
        return None
    return real


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
    if not shutil.which("ffmpeg"):
        raise BridgeError(ffmpeg_missing(audio.suffix.lower()))
    temp_dir = tempfile.mkdtemp(prefix="wyoming-voice-")
    dest = os.path.join(temp_dir, "speech.wav")
    ffmpeg = approved_ffmpeg()
    if not ffmpeg:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise BridgeError(ffmpeg_unpinned())
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


_HOME_CREDENTIALS = (".ssh", ".aws", ".gnupg", ".kube")
_HERMES_PROTECTED = ("state.db", "sessions", "mcp-tokens", "pairing", "vault", "browser-profile")


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _path_is_denied(path: str) -> bool:
    """Refuse credential locations without importing Hermes internals.

    A symlink was already refused by the caller. This also refuses the home
    credential directories, Hermes session and token directories, and a path
    outside HERMES_WRITE_SAFE_ROOT when that variable is set.
    """
    try:
        resolved = os.path.realpath(os.path.expanduser(path))
        home = os.path.realpath(os.path.expanduser("~"))
    except OSError:
        return True
    for name in _HOME_CREDENTIALS:
        if _under(resolved, os.path.join(home, name)):
            return True
    if resolved == os.path.join(home, ".netrc"):
        return True
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        try:
            base = os.path.realpath(os.path.expanduser(hermes_home))
        except OSError:
            return True
        for sub in _HERMES_PROTECTED:
            if _under(resolved, os.path.join(base, sub)):
                return True
    safe = os.environ.get("HERMES_WRITE_SAFE_ROOT") or ""
    roots = []
    for part in safe.split(os.pathsep):
        if not part:
            continue
        try:
            roots.append(os.path.realpath(os.path.expanduser(part)))
        except OSError:
            return True
    if roots and not any(_under(resolved, root) for root in roots):
        return True
    return False


def _local_write_checks() -> tuple[Any, Any]:
    return _path_is_denied, (lambda _path: False)


def _write_guard(path: str, loader: Any = None) -> None:
    load = _local_write_checks if loader is None else loader
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
