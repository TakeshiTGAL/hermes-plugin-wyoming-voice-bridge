"""Register Wyoming speech providers and one describe tool."""
from __future__ import annotations

import json


_REQUIRED = ("register_transcription_provider", "register_tts_provider", "register_tool")

_TOOL_DESCRIPTION = (
    "Ask a Wyoming speech server which models and voices it lists. "
    "Uninstalled rows are returned too. The installed field marks each row. "
    "stt or tts sends one describe. both sends two, one connection each. "
    "Does not send audio or text to speak. which is stt, tts, or both. "
    "A Piper reply that lists every voice can be about 24KB."
)


def _load_local():
    """Relative imports when Hermes loads this as a package. Flat only otherwise."""
    if __package__:
        from .providers import build_providers
        from .service import status
        return build_providers, status
    import sys
    from pathlib import Path

    root = str(Path(__file__).resolve().parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    from providers import build_providers
    from service import status
    return build_providers, status


def register(ctx: object) -> None:
    if any(not callable(getattr(ctx, name, None)) for name in _REQUIRED):
        return
    build_providers, status = _load_local()

    stt, tts = build_providers()
    ctx.register_transcription_provider(stt)
    ctx.register_tts_provider(tts)

    def wyoming_voice_status(args, **_kwargs):
        raw = args or {}
        which = raw.get("which") if isinstance(raw, dict) else ""
        if not isinstance(which, str):
            which = ""
        return json.dumps(status(which.strip().lower()))

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
