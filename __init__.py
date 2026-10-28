"""Register Wyoming speech providers and one describe tool."""
from __future__ import annotations

import json


_REQUIRED = ("register_transcription_provider", "register_tts_provider", "register_tool")

_TOOL_DESCRIPTION = (
    "Wyoming speech server: list models and voices. "
    "Uninstalled rows are returned too. The installed field marks each row. "
    "stt or tts sends one describe. both sends two, one connection each. "
    "Does not send audio or text to speak. which is stt, tts, or both. "
    "It does not transcribe or speak itself: the plugin's stt and tts providers turn audio into a voice transcription "
    "and read text aloud, or synthesize speech, through that server, for example Whisper and Piper. "
    "A Piper reply that lists every voice can be about 24KB."
)


def _load_local():
    """Relative imports when Hermes loads this as a package. Flat only otherwise."""
    if __package__:
        from .gate import on_pre_tool_call
        from .providers import build_providers
        from .service import fold_which, status
        return build_providers, fold_which, status, on_pre_tool_call
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from gate import on_pre_tool_call
    from providers import build_providers
    from service import fold_which, status
    return build_providers, fold_which, status, on_pre_tool_call


def register(ctx: object) -> None:
    if any(not callable(getattr(ctx, name, None)) for name in _REQUIRED):
        return
    build_providers, fold_which, status, on_pre_tool_call = _load_local()

    def _stt_language() -> object:
        getter = getattr(ctx, "get_config", None)
        if not callable(getter):
            return None
        try:
            return getter("stt_language", "")
        except TypeError:
            return getter("stt_language")

    stt, tts = build_providers(_stt_language)
    ctx.register_transcription_provider(stt)
    ctx.register_tts_provider(tts)

    def wyoming_voice_status(args, **kwargs):
        folded = fold_which(args if isinstance(args, dict) else {})
        if isinstance(folded, dict):
            return json.dumps(folded)
        raw = dict(args) if isinstance(args, dict) else {}
        return json.dumps(status(
            folded,
            raw=raw,
            session_id=str(kwargs.get("session_id") or ""),
            task_id=str(kwargs.get("task_id") or ""),
        ))

    ctx.register_tool(
        name="wyoming_voice_status",
        toolset="wyoming_voice",
        schema={
            "name": "wyoming_voice_status",
            "description": _TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "which": {
                        "type": "string",
                        "enum": ["stt", "tts", "both"],
                        "description": "Which configured server to describe: stt, tts, or both.",
                    }
                },
                "required": ["which"],
                "additionalProperties": False,
            },
        },
        handler=wyoming_voice_status,
        description=_TOOL_DESCRIPTION,
    )
    register_hook = getattr(ctx, "register_hook", None)
    if callable(register_hook):
        register_hook("pre_tool_call", on_pre_tool_call)
    try:
        from pathlib import Path
        ctx.register_skill(
            "wyoming-speech",
            Path(__file__).resolve().parent / "skills" / "wyoming-speech" / "SKILL.md",
            description=(
                "Wyoming speech server models and voices. "
                "Before web_search, use tool_search to find wyoming_voice_status and tool_call to run it."
            ),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("wyoming skill was not registered", exc_info=True)
