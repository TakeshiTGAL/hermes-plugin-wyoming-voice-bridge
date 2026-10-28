"""Argument shapes a model is likely to send. No network."""
import json


class _Ctx:
    def register_transcription_provider(self, provider):
        self.stt = provider

    def register_tts_provider(self, provider):
        self.tts = provider

    def register_tool(self, **kwargs):
        self.handler = kwargs["handler"]


def _handler(monkeypatch):
    import service
    from __init__ import register
    from tests.test_language import _stub_bases

    _stub_bases()
    seen = []

    def fake_status(which, **_kwargs):
        seen.append(which)
        return {"success": True}

    monkeypatch.setattr(service, "status", fake_status)
    ctx = _Ctx()
    register(ctx)
    return ctx.handler, seen


def test_which_case_is_described(monkeypatch):
    handler, seen = _handler(monkeypatch)
    body = json.loads(handler({"which": "STT"}))
    assert body["success"] is True
    both = json.loads(handler({"which": "Both"}))
    assert both["success"] is True
    assert seen == ["stt", "both"]


def test_fullwidth_which_is_described(monkeypatch):
    handler, seen = _handler(monkeypatch)
    body = json.loads(handler({"which": "ｓｔｔ"}))
    assert body["success"] is True
    assert seen == ["stt"]


def test_extra_arguments_are_refused_without_the_value(monkeypatch):
    handler, seen = _handler(monkeypatch)
    body = json.loads(handler({"which": "stt", "host": "10.9.9.9", "port": 9}))
    text = json.dumps(body)
    assert body["ok"] is False
    assert body["error_type"] == "bad_args"
    assert "for example which stt" in body["error"]
    assert "10.9.9.9" not in text
    assert "host" not in text
    assert seen == []


def test_missing_which_names_the_three_values(monkeypatch):
    handler, seen = _handler(monkeypatch)
    body = json.loads(handler({}))
    assert body["ok"] is False
    assert body["error_type"] == "bad_args"
    assert "stt, tts, or both" in body["error"]
    assert "for example which stt" in body["error"]
    assert seen == []


def test_numeric_which_is_refused_without_the_number(monkeypatch):
    handler, seen = _handler(monkeypatch)
    for bad in (10.0, "１０"):
        body = json.loads(handler({"which": bad}))
        text = json.dumps(body, ensure_ascii=False)
        assert body["ok"] is False
        assert body["error_type"] == "bad_args"
        assert "for example which stt" in body["error"]
        assert "10.0" not in text
        assert "１０" not in text
        assert seen == []
