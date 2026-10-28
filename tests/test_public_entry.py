"""The shipped build through Hermes's public entry points, with nothing patched in the plugin.

A child process runs the Hermes interpreter on an empty HERMES_HOME with this plugin in
plugins/ and enabled in config.yaml. Hermes discovers it, the pre_tool_call hook returns the
approve line, model_tools.handle_function_call asks the approval callback, and
transcribe_audio and text_to_speech_tool reach a Wyoming peer. The peer is built from the
wyoming library's own AsyncEventHandler, the handler class Wyoming services use.

The installed wyoming tree is checked with the plugin's own table. The library check is not
replaced. With wyoming not installed this test skips; with an unlisted tree it fails.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MARK = "WYOMING_PUBLIC_ENTRY "


def _hermes() -> tuple[str, Path] | None:
    src = os.environ.get("HERMES_SRC") or os.environ.get("HERMES_AGENT_SRC") or ""
    if not src or not (Path(src) / "model_tools.py").is_file():
        return None
    python = os.environ.get("HERMES_AGENT_PYTHON") or ""
    if not python or not Path(python).is_file():
        venv = Path(src) / ".venv" / "bin" / "python"
        python = str(venv) if venv.is_file() else sys.executable
    return python, Path(src)


def _copy_plugin(dest: Path) -> None:
    def skip(_dir, names):
        return [n for n in names if n in {".git", "__pycache__", ".pytest_cache"}]

    shutil.copytree(ROOT, dest, ignore=skip)


def test_shipped_build_asks_once_then_describes_transcribes_and_speaks(tmp_path):
    found = _hermes()
    if found is None:
        pytest.skip("set HERMES_SRC (and HERMES_AGENT_PYTHON) to a Hermes checkout")
    try:
        import wyoming
    except ImportError:
        pytest.skip("wyoming is not installed in this Python")
    python, src = found
    home = tmp_path / "home"
    (home / "plugins").mkdir(parents=True)
    _copy_plugin(home / "plugins" / "wyoming-voice-bridge")
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - wyoming-voice-bridge\n"
        "stt:\n  provider: wyoming\n"
        "tts:\n  provider: wyoming\n",
        encoding="utf-8",
    )
    wav = tmp_path / "in.wav"
    with wave.open(str(wav), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x01" * 8000)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("WYOMING_", "HERMES_"))}
    env["HERMES_HOME"] = str(home)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(Path(wyoming.__file__).resolve().parent.parent), str(src)]
    )
    proc = subprocess.run(
        [python, str(Path(__file__).resolve()), "--driver", str(src), str(wav), str(tmp_path / "out.wav")],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    line = next((x for x in reversed(proc.stdout.splitlines()) if x.startswith(MARK)), "")
    if proc.returncode != 0 or not line:
        pytest.fail(proc.stderr[-3000:] or proc.stdout[-3000:] or "driver printed nothing")
    got = json.loads(line[len(MARK):])
    assert got["loaded"] is True, got
    assert got["tool_registered"] is True, got
    assert got["directive"]["action"] == "approve", got
    assert got["directive"]["message"].startswith("Send 1 Wyoming describe to 127.0.0.1:"), got
    assert got["denied"]["blocked"] is True, got
    assert got["denied"]["describes_sent"] == 0, got
    assert len(got["asked"]) == 2, got
    assert got["status"]["success"] is True, got
    assert got["status"]["stt"]["models"][0]["name"] == "peer-model", got
    assert got["status_describes"] == 1, got
    assert got["stt_available"] is True, got
    assert got["stt"]["success"] is True, got
    assert got["stt"]["transcript"] == "peer heard 16000 bytes", got
    assert got["tts"]["success"] is True, got
    assert got["tts"]["synthesize_sent"] == 1, got
    assert got["tts"]["bytes"] > 0, got
    assert got["other_tool_directive"] is None, got


def _driver() -> None:
    import asyncio
    import threading

    src, wav, out = sys.argv[2], sys.argv[3], sys.argv[4]
    sys.path.insert(0, src)

    from wyoming.asr import Transcribe, Transcript
    from wyoming.audio import AudioChunk, AudioStart, AudioStop
    from wyoming.event import Event
    from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info, TtsProgram, TtsVoice
    from wyoming.server import AsyncEventHandler
    from wyoming.tts import Synthesize

    seen: list[str] = []
    attribution = Attribution(name="test", url="https://example.invalid")
    info = Info(
        asr=[AsrProgram(name="peer", attribution=attribution, installed=True, description=None, version=None,
                        models=[AsrModel(name="peer-model", attribution=attribution, installed=True,
                                         description=None, version=None, languages=["en"])])],
        tts=[TtsProgram(name="peer", attribution=attribution, installed=True, description=None, version=None,
                        voices=[TtsVoice(name="peer-voice", attribution=attribution, installed=True,
                                         description=None, version=None, languages=["en"])])],
    )

    class Handler(AsyncEventHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.audio = 0

        async def handle_event(self, event: Event) -> bool:
            seen.append(event.type)
            if Describe.is_type(event.type):
                await self.write_event(info.event())
                return True
            if Transcribe.is_type(event.type) or AudioStart.is_type(event.type):
                return True
            if AudioChunk.is_type(event.type):
                self.audio += len(AudioChunk.from_event(event).audio)
                return True
            if AudioStop.is_type(event.type):
                await self.write_event(Transcript(text=f"peer heard {self.audio} bytes").event())
                return False
            if Synthesize.is_type(event.type):
                await self.write_event(AudioStart(rate=22050, width=2, channels=1).event())
                await self.write_event(AudioChunk(rate=22050, width=2, channels=1, audio=b"\x00\x00" * 2205).event())
                await self.write_event(AudioStop().event())
                return False
            return True

    ready = threading.Event()
    port = {}

    def serve() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def main() -> None:
            async def on_client(reader, writer):
                await Handler(reader, writer).run()

            srv = await asyncio.start_server(on_client, "127.0.0.1", 0)
            port["n"] = srv.sockets[0].getsockname()[1]
            ready.set()
            async with srv:
                await srv.serve_forever()

        loop.run_until_complete(main())

    threading.Thread(target=serve, daemon=True).start()
    ready.wait(10)
    for side in ("STT", "TTS"):
        os.environ[f"WYOMING_{side}_HOST"] = "127.0.0.1"
        os.environ[f"WYOMING_{side}_PORT"] = str(port["n"])

    import hermes_cli.plugins as hp

    hp.discover_plugins(force=True)
    mgr = hp.get_plugin_manager()
    loaded = any(
        p.manifest.name == "wyoming-voice-bridge" and p.enabled and not p.error
        and "wyoming_voice_status" in p.tools_registered and "pre_tool_call" in p.hooks_registered
        for p in mgr._plugins.values()
    )
    from tools.registry import registry

    result: dict = {"loaded": loaded, "tool_registered": "wyoming_voice_status" in registry.get_all_tool_names()}
    details = hp._get_pre_tool_call_directive_details("wyoming_voice_status", {"which": "stt"})
    result["directive"] = {"action": details.action, "message": details.message}
    other = hp._get_pre_tool_call_directive_details("read_file", {"path": "x"})
    result["other_tool_directive"] = other.action

    import model_tools
    from tools.terminal_tool import set_approval_callback

    os.environ["HERMES_INTERACTIVE"] = "1"
    asked: list[str] = []
    answer = {"value": "deny"}

    def callback(command, description, **_kwargs):
        asked.append(str(description))
        return answer["value"]

    set_approval_callback(callback)
    before = seen.count("describe")
    blocked = model_tools.handle_function_call("wyoming_voice_status", {"which": "stt"},
                                               session_id="s1", task_id="t1")
    result["denied"] = {"blocked": "BLOCKED" in str(blocked), "describes_sent": seen.count("describe") - before}
    answer["value"] = "once"
    before = seen.count("describe")
    raw = model_tools.handle_function_call("wyoming_voice_status", {"which": "stt"},
                                           session_id="s1", task_id="t2")
    result["status"] = json.loads(raw)
    result["status_describes"] = seen.count("describe") - before
    result["asked"] = asked

    from tools.transcription_tools import transcribe_audio
    from tools.tts_tool import text_to_speech_tool

    from agent.transcription_registry import get_provider

    provider = get_provider("wyoming")
    result["stt_available"] = bool(provider is not None and provider.is_available())
    stt = transcribe_audio(wav)
    result["stt"] = {"success": stt.get("success"), "transcript": stt.get("transcript"), "error": stt.get("error")}
    before = seen.count("synthesize")
    tts = json.loads(text_to_speech_tool("Hello from the test.", output_path=out))
    path = Path(str(tts.get("file_path") or ""))
    # The plugin writes a WAV. Hermes may re-encode it for voice delivery with its own ffmpeg.
    result["tts"] = {
        "success": tts.get("success"),
        "error": tts.get("error"),
        "bytes": path.stat().st_size if path.is_file() else 0,
        "synthesize_sent": seen.count("synthesize") - before,
    }
    print(MARK + json.dumps(result, default=str))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--driver":
    _driver()
