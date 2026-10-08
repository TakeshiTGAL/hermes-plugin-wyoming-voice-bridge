"""Language Hermes actually passes into transcribe_audio, on two checkouts.

The trees are siblings of this plugin. A checkout that is not there is skipped.
Preship runs from a git archive, so both tests skip there. Collection does not
import Hermes.
"""
import json
import os
import subprocess
import sys
import wave
from pathlib import Path


def _tree(name: str) -> Path | None:
    sibling = Path(__file__).resolve().parents[2] / name
    if (sibling / "tools" / "transcription_tools.py").is_file():
        return sibling
    return None


def _wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x01" * 1600)


def _interpreter(hermes: Path) -> str:
    venv = hermes / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


def _run_tree(name: str, tmp_path: Path) -> None:
    import pytest
    import wyoming

    hermes = _tree(name)
    if hermes is None:
        pytest.skip("Hermes tree is not on this machine")
    wav = tmp_path / "in.wav"
    _wav(wav)
    home = tmp_path / "hermes-home"
    home.mkdir()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("WYOMING_") or key == "HERMES_LOCAL_STT_LANGUAGE":
            env.pop(key, None)
    env["HERMES_HOME"] = str(home)
    # The checkout's interpreter has Hermes. This process has wyoming 1.5.4.
    env["PYTHONPATH"] = str(Path(wyoming.__file__).resolve().parent.parent)
    proc = subprocess.run(
        [
            _interpreter(hermes),
            str(Path(__file__).resolve()),
            "--driver",
            str(hermes),
            str(Path(__file__).resolve().parents[1]),
            str(wav),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    marker = "WYOMING_LANG_RESULT "
    line = next((item for item in reversed(proc.stdout.splitlines()) if item.startswith(marker)), "")
    if proc.returncode != 0 or not line:
        pytest.fail(proc.stderr[-2000:] or proc.stdout[-2000:] or "driver produced no result")
    _run_seeded(name, tmp_path, hermes, env)
    body = json.loads(line[len(marker):])
    expect = {
        "default_plus_env": "ja",
        "raw_language_only": "ja",
        "section_over_raw_and_env": "ja",
        "hermes_local_only": "ja",
        "hook": "de",
        "hook_same_as_resolution": "ja",
        "voice_mode_default": "ja",
        "voice_mode_default_other": "en",
        "voice_mode_no_key": "ja",
        "voice_mode_no_key_other": None,
        "user_wrote_en": "en",
        "raw_en_under_wyoming_env": "ja",
        "omit": None,
        "raw_unreadable": "ja",
    }
    got = {item["name"]: item for item in body["results"]}
    assert set(got) == set(expect)
    for name, language in expect.items():
        item = got[name]
        assert item["success"] is True, item
        assert item["language"] == language, item
        if language is None:
            assert item["present"] is False


def _run_seeded(name: str, tmp_path: Path, hermes: Path, env: dict) -> None:
    """Installer example on disk, through the real config reader."""
    import pytest

    wav = tmp_path / "seeded.wav"
    _wav(wav)
    home = tmp_path / f"seeded-{name}"
    home.mkdir()
    child = dict(env)
    child["HERMES_HOME"] = str(home)
    proc = subprocess.run(
        [
            _interpreter(hermes),
            str(Path(__file__).resolve()),
            "--seeded",
            str(hermes),
            str(Path(__file__).resolve().parents[1]),
            str(wav),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=child,
        timeout=180,
    )
    marker = "WYOMING_LANG_RESULT "
    line = next((item for item in reversed(proc.stdout.splitlines()) if item.startswith(marker)), "")
    if proc.returncode != 0 or not line:
        pytest.fail(proc.stderr[-2000:] or proc.stdout[-2000:] or "seeded driver produced no result")
    body = json.loads(line[len(marker):])
    expect = {
        "seeded_example": "ja",
        "seeded_hook_de": "de",
        "seeded_section": "ja",
        "user_file_en": "ja",
        "user_file_en_only": "en",
        "user_file_ja": "en",
        "voice_default": "ja",
        "voice_default_other": "en",
        "voice_no_key": "ja",
        "voice_no_key_other": None,
    }
    got = {item["name"]: item for item in body["results"]}
    assert set(got) == set(expect)
    for case, language in expect.items():
        item = got[case]
        assert item["success"] is True, item
        assert item["language"] == language, item


def test_transcribe_audio_on_hermes_main(tmp_path):
    _run_tree("hermes-agent-ref", tmp_path)


def test_transcribe_audio_on_hermes_v0214(tmp_path):
    _run_tree("hermes-agent-ref-v0214", tmp_path)


def _driver() -> None:
    hermes = sys.argv[2]
    plugin = sys.argv[3]
    wav = sys.argv[4]
    sys.path.insert(0, plugin)
    sys.path.insert(0, hermes)

    import hermes_cli.config as hermes_config
    import hermes_cli.plugins as plugins_mod

    state = {"raw": {}, "raw_fails": False, "loaded": {}, "hook": None, "hook_kind": None}

    def load_config():
        return {"stt": dict(state["loaded"])}

    def read_raw_config():
        if state["raw_fails"]:
            raise OSError("config cannot be read")
        return {"stt": state["raw"]}

    def has_hook(name: str) -> bool:
        return state["hook_kind"] is not None and name == "pre_transcription"

    def invoke_hook(_name: str, **kwargs):
        if state["hook_kind"] == "voice":
            if kwargs.get("source") == "voice_mode":
                return [{"language": "ja"}]
            return [{}]
        return [{"language": state["hook"]}]

    def ensure(*_args, **_kwargs):
        return None

    hermes_config.load_config = load_config
    hermes_config.read_raw_config = read_raw_config
    plugins_mod.has_hook = has_hook
    plugins_mod.invoke_hook = invoke_hook
    plugins_mod._ensure_plugins_discovered = ensure

    import importlib.util

    from agent.transcription_registry import register_provider
    from tools.transcription_tools import transcribe_audio

    spec = importlib.util.spec_from_file_location(
        "wyoming_bridge_providers",
        str(Path(plugin) / "providers.py"),
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    fake_spec = importlib.util.spec_from_file_location(
        "wyoming_fake_server",
        str(Path(plugin) / "tests" / "fake_server.py"),
    )
    fake_mod = importlib.util.module_from_spec(fake_spec)
    fake_spec.loader.exec_module(fake_mod)
    FakeWyoming = fake_mod.FakeWyoming

    recorded: list[dict] = []

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is None:
            writer.close()
            return
        if event.type == "describe":
            info = {"asr": [{"name": "whisper", "models": [{
                "name": "tiny",
                "languages": ["ja", "en", "fr", "de"],
                "installed": True,
            }]}]}
            await async_write_event(Event(type="info", data=info), writer)
            writer.close()
            return
        if event.type == "transcribe":
            data = event.data if isinstance(event.data, dict) else {}
            recorded.append(data)
            while True:
                nxt = await async_read_event(reader)
                if nxt is None or nxt.type == "audio-stop":
                    break
            await async_write_event(Event(type="transcript", data={"text": "ok"}), writer)
        writer.close()

    cases = [
        {
            "name": "default_plus_env",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": "ja",
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "raw_language_only",
            "raw": {"provider": "wyoming", "language": "ja"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "ja"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "section_over_raw_and_env",
            "raw": {"provider": "wyoming", "language": "fr", "wyoming": {"language": "ja"}},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "fr", "wyoming": {"language": "ja"}},
            "wyoming_env": "en",
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "hermes_local_only",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": "ja",
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "hook",
            "raw": {"provider": "wyoming", "language": "fr", "wyoming": {"language": "ja"}},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "fr", "wyoming": {"language": "ja"}},
            "wyoming_env": "en",
            "local_env": None,
            "hook": "de",
            "raw_fails": False,
        },
        {
            "name": "hook_same_as_resolution",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": "ja",
            "local_env": None,
            "hook": "en",
            "hook_kind": "const",
            "source": None,
            "raw_fails": False,
        },
        {
            "name": "voice_mode_default",
            "raw": {"provider": "wyoming", "language": "en"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "hook_kind": "voice",
            "source": "voice_mode",
            "raw_fails": False,
        },
        {
            "name": "voice_mode_default_other",
            "raw": {"provider": "wyoming", "language": "en"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "hook_kind": "voice",
            "source": "gateway",
            "raw_fails": False,
        },
        {
            "name": "voice_mode_no_key",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "hook_kind": "voice",
            "source": "voice_mode",
            "raw_fails": False,
        },
        {
            "name": "voice_mode_no_key_other",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "hook_kind": "voice",
            "source": "gateway",
            "raw_fails": False,
        },
        {
            "name": "user_wrote_en",
            "raw": {"provider": "wyoming", "language": "en"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "raw_en_under_wyoming_env",
            "raw": {"provider": "wyoming", "language": "en"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": "ja",
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "omit",
            "raw": {"provider": "wyoming"},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": None,
            "local_env": None,
            "hook": None,
            "raw_fails": False,
        },
        {
            "name": "raw_unreadable",
            "raw": {"provider": "wyoming", "language": "fr", "wyoming": {"language": "de"}},
            "loaded": {"enabled": True, "provider": "wyoming", "language": "en"},
            "wyoming_env": "ja",
            "local_env": None,
            "hook": None,
            "raw_fails": True,
        },
    ]

    results = []
    with FakeWyoming(handler) as server:
        os.environ["WYOMING_STT_HOST"] = "127.0.0.1"
        os.environ["WYOMING_STT_PORT"] = str(server.port)
        os.environ.pop("WYOMING_STT_MODEL", None)
        register_provider(bridge.build_providers()[0])
        for case in cases:
            state["raw"] = case["raw"]
            state["loaded"] = case["loaded"]
            state["hook"] = case["hook"]
            state["hook_kind"] = case.get("hook_kind")
            if state["hook_kind"] is None and case["hook"] is not None:
                state["hook_kind"] = "const"
            state["raw_fails"] = case["raw_fails"]
            if case["wyoming_env"] is None:
                os.environ.pop("WYOMING_STT_LANGUAGE", None)
            else:
                os.environ["WYOMING_STT_LANGUAGE"] = case["wyoming_env"]
            if case["local_env"] is None:
                os.environ.pop("HERMES_LOCAL_STT_LANGUAGE", None)
            else:
                os.environ["HERMES_LOCAL_STT_LANGUAGE"] = case["local_env"]
            recorded.clear()
            result = transcribe_audio(wav, source=case.get("source"))
            data = recorded[-1] if recorded else {}
            results.append({
                "name": case["name"],
                "success": result.get("success") is True,
                "error": "" if result.get("success") is True else str(result.get("error", ""))[:300],
                "present": "language" in data,
                "language": data.get("language") if "language" in data else None,
                "events": len(recorded),
            })
    print("WYOMING_LANG_RESULT " + json.dumps({"results": results}))


def _seeded_driver() -> None:
    hermes = Path(sys.argv[2])
    plugin = sys.argv[3]
    wav = sys.argv[4]
    sys.path.insert(0, plugin)
    sys.path.insert(0, str(hermes))

    import hermes_cli.plugins as plugins_mod

    plugins_mod._ensure_plugins_discovered = lambda *_args, **_kwargs: None

    import importlib.util

    from agent.transcription_registry import register_provider
    from hermes_cli.plugins import PluginContext, get_plugin_manager
    from hermes_cli.plugins_manifest import PluginManifest
    from tools.transcription_tools import transcribe_audio

    spec = importlib.util.spec_from_file_location(
        "wyoming_bridge_providers",
        str(Path(plugin) / "providers.py"),
    )
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    fake_spec = importlib.util.spec_from_file_location(
        "wyoming_fake_server",
        str(Path(plugin) / "tests" / "fake_server.py"),
    )
    fake_mod = importlib.util.module_from_spec(fake_spec)
    fake_spec.loader.exec_module(fake_mod)
    FakeWyoming = fake_mod.FakeWyoming

    recorded: list[dict] = []

    async def handler(reader, writer):
        from wyoming.event import Event, async_read_event, async_write_event

        event = await async_read_event(reader)
        if event is None:
            writer.close()
            return
        if event.type == "describe":
            info = {"asr": [{"name": "whisper", "models": [{
                "name": "tiny",
                "languages": ["ja", "en", "fr", "de"],
                "installed": True,
            }]}]}
            await async_write_event(Event(type="info", data=info), writer)
            writer.close()
            return
        if event.type == "transcribe":
            data = event.data if isinstance(event.data, dict) else {}
            recorded.append(data)
            while True:
                nxt = await async_read_event(reader)
                if nxt is None or nxt.type == "audio-stop":
                    break
            await async_write_event(Event(type="transcript", data={"text": "ok"}), writer)
        writer.close()

    example = (hermes / "cli-config.yaml.example").read_text(encoding="utf-8")
    needle = "\nstt:\n"
    if needle not in example:
        raise RuntimeError("example has no stt block")
    seeded = example.replace(needle, "\nstt:\n  provider: \"wyoming\"\n", 1)
    seeded_section = example.replace(
        needle,
        "\nstt:\n  provider: \"wyoming\"\n  wyoming:\n    language: ja\n",
        1,
    )
    home = Path(os.environ["HERMES_HOME"])
    config_path = home / "config.yaml"
    no_key = "stt:\n  enabled: true\n  provider: wyoming\n"
    cases = [
        ("seeded_example", seeded, "ja", None, None),
        ("seeded_hook_de", seeded, "ja", "de", None),
        ("seeded_section", seeded_section, "en", None, None),
        ("user_file_en", "stt:\n  enabled: true\n  provider: wyoming\n  language: \"en\"\n", "ja", None, None),
        ("user_file_en_only", "stt:\n  enabled: true\n  provider: wyoming\n  language: \"en\"\n", None, None, None),
        ("user_file_ja", "stt:\n  enabled: true\n  provider: wyoming\n  language: ja\n", "en", None, None),
        ("voice_default", seeded, None, "voice", "voice_mode"),
        ("voice_default_other", seeded, None, "voice", None),
        ("voice_no_key", no_key, None, "voice", "voice_mode"),
        ("voice_no_key_other", no_key, None, "voice", "gateway"),
    ]

    def constant_de(**_kwargs):
        return {"language": "de"}

    def voice_ja(**kwargs):
        if kwargs.get("source") == "voice_mode":
            return {"language": "ja"}
        return {}

    results = []
    with FakeWyoming(handler) as server:
        os.environ["WYOMING_STT_HOST"] = "127.0.0.1"
        os.environ["WYOMING_STT_PORT"] = str(server.port)
        os.environ.pop("WYOMING_STT_MODEL", None)
        os.environ.pop("HERMES_LOCAL_STT_LANGUAGE", None)
        register_provider(bridge.build_providers()[0])
        manager = get_plugin_manager()
        manager._discovered = True
        manifest = PluginManifest(
            name="en-default-hook", version="0.0.1", provides_hooks=["pre_transcription"],
        )
        ctx = PluginContext(manifest, manager)
        for name, text, wyoming_env, hook_name, source in cases:
            config_path.write_text(text, encoding="utf-8")
            if wyoming_env is None:
                os.environ.pop("WYOMING_STT_LANGUAGE", None)
            else:
                os.environ["WYOMING_STT_LANGUAGE"] = wyoming_env
            manager._hooks.pop("pre_transcription", None)
            if hook_name == "de":
                ctx.register_hook("pre_transcription", constant_de)
            elif hook_name == "voice":
                ctx.register_hook("pre_transcription", voice_ja)
            recorded.clear()
            result = transcribe_audio(wav, source=source)
            data = recorded[-1] if recorded else {}
            results.append({
                "name": name,
                "success": result.get("success") is True,
                "error": "" if result.get("success") is True else str(result.get("error", ""))[:300],
                "language": data.get("language") if "language" in data else None,
            })
    print("WYOMING_LANG_RESULT " + json.dumps({"results": results}))


if __name__ == "__main__" and "--driver" in sys.argv:
    try:
        _driver()
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise

if __name__ == "__main__" and "--seeded" in sys.argv:
    try:
        _seeded_driver()
    except Exception as exc:
        sys.stderr.write(f"{type(exc).__name__}: {exc}\n")
        raise
