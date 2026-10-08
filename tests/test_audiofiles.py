import sys
import types

import pytest

from audiofiles import _write_guard, write_wav
from session import BridgeError


def _pcm() -> bytes:
    return b"\x00\x01" * 16


def test_existing_wav_is_not_replaced(tmp_path):
    sibling = tmp_path / "keep.wav"
    sibling.write_bytes(b"keep-me")

    def guard(_path):
        return None

    with pytest.raises(BridgeError) as caught:
        write_wav(str(tmp_path / "keep.mp3"), 16000, 2, 1, _pcm(), guard=guard)
    assert "did not write over it" in caught.value.message
    assert "deletes it" in caught.value.message
    assert sibling.read_bytes() == b"keep-me"
    assert list(tmp_path.iterdir()) == [sibling]


def test_each_write_check_fails_three_ways(tmp_path):
    dest = tmp_path / "out.wav"

    def expect(loader):
        with pytest.raises(BridgeError) as caught:
            _write_guard(str(dest), loader)
        assert "Refusing to write" in caught.value.message
        assert not dest.exists()

    def cannot_import():
        raise ImportError("agent.file_safety")

    def renamed():
        raise AttributeError("is_write_denied")

    def denied_raises():
        def boom(_path):
            raise RuntimeError("is_write_denied")
        return boom, (lambda _path: False)

    def approval_raises():
        def boom(_path):
            raise RuntimeError("is_write_approval_required")
        return (lambda _path: False), boom

    def denied_renamed():
        return None, (lambda _path: False)

    def approval_renamed():
        return (lambda _path: False), None

    expect(cannot_import)
    expect(renamed)
    expect(denied_raises)
    expect(approval_raises)
    expect(denied_renamed)
    expect(approval_renamed)


def test_real_import_notices_a_renamed_check(tmp_path, monkeypatch):
    agent = types.ModuleType("agent")
    safety = types.ModuleType("agent.file_safety")
    safety.is_write_denied = lambda _path: False
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.file_safety", safety)
    with pytest.raises(BridgeError) as caught:
        _write_guard(str(tmp_path / "out.wav"))
    assert "Refusing to write" in caught.value.message
