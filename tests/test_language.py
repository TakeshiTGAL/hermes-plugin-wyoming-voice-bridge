"""Language order, without reading the user's Hermes config."""
import sys
import types

from providers import RAW_UNREADABLE, build_providers, choose_request_language


def test_env_wins_over_the_filled_in_default():
    assert choose_request_language(
        "en",
        wyoming_env="ja",
        local_env=None,
        raw_stt={},
        loaded_resolution="en",
    ) == "ja"


def test_user_written_raw_language_is_sent():
    assert choose_request_language(
        "ja",
        wyoming_env=None,
        local_env=None,
        raw_stt={"language": "ja"},
        loaded_resolution="ja",
    ) == "ja"


def test_section_beats_raw_language_and_env():
    assert choose_request_language(
        "ja",
        wyoming_env="en",
        local_env="en",
        raw_stt={"language": "fr", "wyoming": {"language": "ja"}},
        loaded_resolution="ja",
    ) == "ja"


def test_hermes_local_env_is_used_when_no_raw_key_is_written():
    assert choose_request_language(
        "en",
        wyoming_env=None,
        local_env="ja",
        raw_stt={},
        loaded_resolution="en",
    ) == "ja"


def test_same_string_as_the_resolution_is_not_a_hook():
    assert choose_request_language(
        "en",
        wyoming_env="ja",
        local_env=None,
        raw_stt={},
        loaded_resolution="en",
    ) == "ja"


def test_a_different_passed_language_is_the_hook():
    assert choose_request_language(
        "de",
        wyoming_env="en",
        local_env=None,
        raw_stt={"language": "fr", "wyoming": {"language": "ja"}},
        loaded_resolution="ja",
    ) == "de"


def test_hook_wins_over_the_section():
    assert choose_request_language(
        "de",
        wyoming_env="en",
        local_env=None,
        raw_stt={"language": "fr", "wyoming": {"language": "ja"}},
        loaded_resolution="ja",
    ) == "de"


def test_wyoming_env_beats_raw_stt_language():
    assert choose_request_language(
        "en",
        wyoming_env="ja",
        local_env=None,
        raw_stt={"language": "en"},
        loaded_resolution="en",
    ) == "ja"
    assert choose_request_language(
        "ja",
        wyoming_env="en",
        local_env=None,
        raw_stt={"language": "ja"},
        loaded_resolution="ja",
    ) == "en"
    assert choose_request_language(
        "ja",
        wyoming_env=None,
        local_env="en",
        raw_stt={"language": "ja"},
        loaded_resolution="ja",
    ) == "ja"


def test_user_written_en_is_sent():
    assert choose_request_language(
        "en",
        wyoming_env=None,
        local_env=None,
        raw_stt={"language": "en"},
        loaded_resolution="en",
    ) == "en"


def test_no_key_no_env_and_no_hook_omits_language():
    assert choose_request_language(
        "en",
        wyoming_env=None,
        local_env=None,
        raw_stt={},
        loaded_resolution="en",
    ) is None


def test_unreadable_raw_config_skips_to_the_env():
    assert choose_request_language(
        "en",
        wyoming_env="ja",
        local_env=None,
        raw_stt=RAW_UNREADABLE,
        loaded_resolution="en",
    ) == "ja"


def test_empty_and_the_word_default_are_skipped():
    assert choose_request_language(
        "default",
        wyoming_env="  ",
        local_env="default",
        raw_stt={"language": "default", "wyoming": {"language": ""}},
        loaded_resolution="en",
    ) is None
    assert choose_request_language(
        "Default",
        wyoming_env=None,
        local_env=None,
        raw_stt={},
        loaded_resolution="en",
    ) == "Default"


def test_hook_word_default_falls_through_to_the_section():
    assert choose_request_language(
        "default",
        wyoming_env="ja",
        local_env=None,
        raw_stt={"wyoming": {"language": "fr"}},
        loaded_resolution="en",
    ) == "fr"


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


def _providers(monkeypatch, raw, resolution):
    _stub_bases()
    monkeypatch.setattr("providers._read_raw_stt", lambda: raw)
    monkeypatch.setattr("providers._loaded_resolution", lambda: resolution)
    return build_providers()


def test_provider_sends_env_language_instead_of_filled_in_en(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    monkeypatch.delenv("HERMES_LOCAL_STT_LANGUAGE", raising=False)
    stt, _tts = _providers(monkeypatch, {}, "en")
    result = stt.transcribe("clip.wav", language="en")
    assert result["success"] is True
    assert seen["language"] == "ja"
    assert seen["env_language"] is None


def test_provider_sends_a_passed_language_that_differs(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    monkeypatch.delenv("HERMES_LOCAL_STT_LANGUAGE", raising=False)
    stt, _tts = _providers(
        monkeypatch,
        {"language": "fr", "wyoming": {"language": "ja"}},
        "ja",
    )
    result = stt.transcribe("clip.wav", language="de")
    assert result["success"] is True
    assert seen["language"] == "de"


def test_provider_sends_env_ahead_of_raw_en(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.setenv("WYOMING_STT_LANGUAGE", "ja")
    stt, _tts = _providers(monkeypatch, {"language": "en"}, "en")
    stt.transcribe("clip.wav", language="en")
    assert seen["language"] == "ja"


def test_provider_ignores_speed_and_a_hint(monkeypatch):
    seen = {}

    def fake(_path, **kwargs):
        seen.update(kwargs)
        return {"success": True, "transcript": "ok", "provider": "wyoming"}

    monkeypatch.setattr("providers.transcribe_file", fake)
    monkeypatch.delenv("WYOMING_STT_LANGUAGE", raising=False)
    monkeypatch.delenv("HERMES_LOCAL_STT_LANGUAGE", raising=False)
    stt, tts = _providers(monkeypatch, {}, "en")
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
