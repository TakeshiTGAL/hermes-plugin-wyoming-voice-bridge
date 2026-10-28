"""First request, one describe approval, and one retry from the reply."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from service import fold_which, status

ROOT = Path(__file__).resolve().parents[1]
PHRASES = ("声の一覧", "モデルの一覧", "文字起こしできる", "読み上げの声", "サーバは生きてる")

pytest.importorskip("wyoming")


def _describe(_endpoint, timeout=10):
    return {
        "asr": [{"name": "tiny-int8", "installed": True, "languages": ["en"]}],
        "tts": [{"name": "en_US-lessac-medium", "installed": True, "languages": ["en"]}],
    }


def _clear(monkeypatch):
    for name in (
        "WYOMING_STT_HOST", "WYOMING_STT_PORT", "WYOMING_TTS_HOST", "WYOMING_TTS_PORT",
        "WYOMING_STT_MODEL", "WYOMING_STT_LANGUAGE", "WYOMING_TTS_VOICE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_skill_puts_each_japanese_request_on_an_english_search_line():
    text = (ROOT / "skills" / "wyoming-speech" / "SKILL.md").read_text(encoding="utf-8")
    assert "tool_search" in text and "English" in text
    for phrase in PHRASES:
        line = next(row for row in text.splitlines() if phrase in row)
        assert "tool_search" in line and ("Wyoming" in line or "speech" in line)


def test_readme_first_request_has_five_steps_and_names_the_protocol():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## First request", 1)[1].split("\n## ", 1)[0]
    assert len(re.findall(r"(?m)^\d+\. ", section)) == 5
    assert "which stt" in section
    assert "only when you want voice mode" in section
    description = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))["description"]
    assert description.startswith("Speech recognition and speech synthesis")
    assert "Wyoming is the voice assistant protocol Home Assistant uses" in description


def test_a_missing_host_names_the_settings_and_a_describe_asks_once(monkeypatch):
    _clear(monkeypatch)
    folded = fold_which({"which": ""})
    assert isinstance(folded, dict) and folded["success"] is False
    assert "which stt" in folded["error"]
    import wyoming_pin

    shipped = wyoming_pin.library_status
    monkeypatch.setattr("wyoming_pin.library_status", lambda: "unpinned")
    blocked = status("stt", describe_fn=_describe, approver=lambda _targets: None)
    assert blocked["success"] is False
    assert "sha256" in blocked["error"]
    assert "pip install wyoming==1.5.4" in blocked["error"]
    assert "WYOMING_STT_HOST" not in blocked["error"]
    monkeypatch.setattr("wyoming_pin.library_status", shipped)
    assert shipped() == "ready"
    bare = status("stt", describe_fn=_describe, approver=lambda _targets: None)
    assert bare["success"] is False
    error = bare["error"]
    assert "WYOMING_STT_HOST" in error and "WYOMING_STT_PORT" in error
    assert error.index("Set WYOMING_STT_HOST") < error.index("日本語")
    monkeypatch.setenv("WYOMING_STT_HOST", "127.0.0.1")
    monkeypatch.setenv("WYOMING_STT_PORT", "10300")
    asked = []

    def approver(targets):
        asked.append(list(targets))
        return None

    ready = status("stt", describe_fn=_describe, approver=approver)
    assert ready["success"] is True
    assert len(asked) == 1
    assert asked[0] == ["127.0.0.1:10300"]
