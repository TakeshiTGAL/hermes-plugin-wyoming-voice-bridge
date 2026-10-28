"""ffmpeg starts only when its sha256 is listed for this OS and CPU."""
import hashlib
import platform
import sys
import tempfile
from pathlib import Path

import pytest

from audiofiles import FFMPEG_SHA256, load_pcm_wav
from messages import ffmpeg_unpinned
from session import BridgeError


def test_shipped_table_is_empty():
    assert FFMPEG_SHA256 == {}


def test_a_symlink_ffmpeg_is_refused_before_realpath(tmp_path, monkeypatch):
    target = tmp_path / "real-ffmpeg"
    target.write_bytes(b"real-binary")
    target.chmod(0o755)
    link = tmp_path / "ffmpeg"
    link.symlink_to(target)
    started = []

    monkeypatch.setattr("audiofiles.shutil.which", lambda name: str(link) if name == "ffmpeg" else None)
    monkeypatch.setattr("audiofiles.subprocess.run", lambda *args, **kwargs: started.append(args))
    listed = hashlib.sha256(target.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "audiofiles.FFMPEG_SHA256",
        {(sys.platform, platform.machine()): frozenset({listed})},
    )
    clip = tmp_path / "clip.flac"
    clip.write_bytes(b"not audio")
    with pytest.raises(BridgeError) as caught:
        load_pcm_wav(str(clip))
    assert caught.value.message == ffmpeg_unpinned()
    assert started == []


def test_unlisted_ffmpeg_is_not_started(tmp_path, monkeypatch):
    fake = tmp_path / "ffmpeg"
    fake.write_bytes(b"not-the-real-binary")
    fake.chmod(0o755)
    other = tmp_path / "other-ffmpeg"
    other.write_bytes(b"a-different-binary")
    other.chmod(0o755)
    started = []
    made = []

    def which(name):
        return str(fake) if name == "ffmpeg" else None

    real_mkdtemp = tempfile.mkdtemp

    def mkdtemp(*_args, **_kwargs):
        path = real_mkdtemp(prefix="wyoming-voice-", dir=tmp_path)
        made.append(path)
        return path

    monkeypatch.setattr("audiofiles.shutil.which", which)
    monkeypatch.setattr("audiofiles.tempfile.mkdtemp", mkdtemp)
    monkeypatch.setattr("audiofiles.subprocess.run", lambda *args, **kwargs: started.append(args))
    listed = hashlib.sha256(other.read_bytes()).hexdigest()
    monkeypatch.setattr(
        "audiofiles.FFMPEG_SHA256",
        {(sys.platform, platform.machine()): frozenset({listed})},
    )
    clip = tmp_path / "clip.flac"
    clip.write_bytes(b"not audio")
    with pytest.raises(BridgeError) as caught:
        load_pcm_wav(str(clip))
    assert caught.value.message == ffmpeg_unpinned()
    assert started == []
    assert made
    assert all(not Path(path).exists() for path in made)
