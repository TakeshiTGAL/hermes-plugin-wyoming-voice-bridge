"""Recognition language is the plugin setting only.

The language Hermes passes, stt.language, hooks, and the process environment are not sources.
"""
import sys
import types

from providers import build_providers, language_from_config, read_plugin_language


def test_empty_and_the_word_default_send_nothing():
    assert language_from_config("") is None
    assert language_from_config("  ") is None
    assert language_from_config("default") is None
    assert language_from_config("Default") is None
    assert language_from_config(" DEFAULT ") is None
    assert language_from_config("en") == "en"
    assert language_from_config("ja") == "ja"
    assert language_from_config(None) is None
    assert language_from_config(1) is None


def test_a_reader_error_sends_nothing():
    def boom():
        raise OSError("config")

    assert read_plugin_language(boom) is None
    assert read_plugin_language(None) is None
    assert read_plugin_language(lambda: " fr ") == "fr"


def _stub_bases():
    if "agent.transcription_provider" in sys.modules and "agent.tts_provider" in sys.modules:
        return
    agent = sys.modules.get("agent") or types.ModuleType("agent")
    sys.modules["agent"] = agent
    for module_name, class_name in (
        ("transcription_provider", "TranscriptionProvider"),
        ("tts_provider", "TTSProvider"),
    ):
        key = f"agent.{module_name}"
        if key in sys.modules:
            continue
        module = types.ModuleType(key)
        setattr(module, class_name, type(class_name, (), {}))
        sys.modules[key] = module
        setattr(agent, module_name, module)


def _providers(read):
    _stub_bases()
    return build_providers(read)


def test_provider_uses_the_setting_and_ignores_the_passed_language(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    monkeypatch.setenv("HERMES_LOCAL_STT_LANGUAGE", "de")
    stt, _tts = _providers(lambda: "fr")
    result = stt.transcribe("clip.wav", language="en")
    assert result["success"] is True
    assert seen["language"] == "fr"
    assert seen["env_language"] is None


def test_provider_omits_the_word_default(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    stt, _tts = _providers(lambda: "Default")
    stt.transcribe("clip.wav", language="ja")
    assert seen["language"] is None


def test_provider_omits_language_when_the_reader_raises(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    def boom():
        raise RuntimeError("unreadable")

    monkeypatch.setattr("providers.transcribe_file", fake)
    stt, _tts = _providers(boom)
    stt.transcribe("clip.wav", language="en")
    assert seen["language"] is None


def test_provider_ignores_speed_and_a_hint(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    monkeypatch.setenv("HERMES_LOCAL_STT_LANGUAGE", "de")
    stt, tts = _providers(lambda: "")
    stt.transcribe("clip.wav", language="en", prompt="hint", speed=2)
    assert "prompt" not in seen
    assert "speed" not in seen
    assert seen["language"] is None

    spoken = {}

    def synth(*_args, **kwargs):
        spoken.update(kwargs)
        return "out.wav"

    monkeypatch.setattr("providers.synthesize_to", synth)
    tts.synthesize("Hello.", "out.wav", speed=1.5, voice="default", prompt="hint")
    assert "speed" not in spoken
    assert "prompt" not in spoken
    assert spoken["voice"] == "default"


def test_register_reads_stt_language_through_get_config(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    _stub_bases()
    from __init__ import register

    class Ctx:
        def __init__(self):
            self.asked = []

        def get_config(self, key, default=""):
            self.asked.append((key, default))
            return "fr"

        def register_tool(self, **_kwargs):
            return None

        def register_transcription_provider(self, provider):
            self.provider = provider

        def register_tts_provider(self, _provider):
            return None

    ctx = Ctx()
    register(ctx)
    assert ctx.asked == []
    result = ctx.provider.transcribe("clip.wav", language="de")
    assert result["success"] is True
    assert ctx.asked == [("stt_language", "")]
    assert seen["language"] == "fr"
