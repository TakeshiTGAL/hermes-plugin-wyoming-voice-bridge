"""Tool Search listing: first sentence is at most 60 characters and not a mechanism line."""
import importlib.util
import re
import sys
from pathlib import Path

_END = re.compile(r"(?<!\be\.g)(?<!\bi\.e)(?<!\betc)[.!?](?=\s|$)")
_BAD = (
    "read-only",
    "take no arguments",
    "takes no arguments",
    "get /",
    "post /",
    "put /",
    "delete /",
)


def _first(text):
    text = " ".join((text or "").split())
    match = _END.search(text)
    return text[: match.end()] if match else text


def _assert_listing(name, description):
    sentence = _first(description)
    assert len(sentence) <= 60, (name, len(sentence), sentence)
    assert len(description) <= 1024, (name, len(description))
    lowered = sentence.lower()
    for prefix in _BAD:
        assert not lowered.startswith(prefix), sentence
    return sentence


class _Ctx:
    def __init__(self):
        self.found = {}

    def register_tool(self, *args, **kwargs):
        schema = kwargs.get("schema")
        name = kwargs.get("name")
        if args:
            name = name or args[0]
            if len(args) >= 3 and schema is None:
                schema = args[2]
        description = None
        if isinstance(schema, dict):
            description = schema.get("description")
            name = name or schema.get("name")
        if description is None:
            description = kwargs.get("description")
        if name and isinstance(description, str):
            self.found[name] = description

    def __getattr__(self, _name):
        def _noop(*_args, **_kwargs):
            return None
        return _noop


def _load_entry():
    root = Path(__file__).resolve().parents[1]
    name = "toolsearch_entry_" + re.sub(r"\W", "_", root.name)
    spec = importlib.util.spec_from_file_location(
        name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_tool_search_first_sentences():
    module = _load_entry()
    if hasattr(module, "_TOOL_DESCRIPTION"):
        sentence = _assert_listing("wyoming_voice_status", module._TOOL_DESCRIPTION)
        print("wyoming_voice_status: " + sentence)
        return
    ctx = _Ctx()
    module.register(ctx)
    assert ctx.found, "no tools registered"
    lines = []
    for name, description in ctx.found.items():
        lines.append(name + ": " + _assert_listing(name, description))
    print("\n".join(lines))
