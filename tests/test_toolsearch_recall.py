"""Ten English requests rank this plugin in Tool Search top 5, beside Hermes core tools."""
import importlib.util
import re
import os
import subprocess
import sys
from pathlib import Path

QUERIES = ['Wyoming speech server', 'Wyoming TTS voices', 'Wyoming speech models', 'list Wyoming voices', 'Wyoming protocol voices', 'local Wyoming speech server', 'Wyoming voice list', 'Wyoming TTS models', 'speech server voices Wyoming', 'Wyoming STT models']

class _Ctx:
    def __init__(self):
        self.tools = []

    def register_tool(self, *args, **kwargs):
        schema = kwargs.get("schema")
        name = kwargs.get("name")
        toolset = kwargs.get("toolset")
        if args:
            name = name or args[0]
            if len(args) >= 2 and toolset is None:
                toolset = args[1]
            if len(args) >= 3 and schema is None:
                schema = args[2]
        if isinstance(schema, dict):
            name = name or schema.get("name")
            schema = dict(schema)
            schema["name"] = name
        if name and isinstance(schema, dict):
            self.tools.append({"name": name, "toolset": toolset or "", "schema": schema})

    def __getattr__(self, _name):
        def _noop(*_a, **_k):
            return None
        return _noop


def _hermes_paths():
    python = os.environ.get("HERMES_AGENT_PYTHON", "")
    src = os.environ.get("HERMES_AGENT_SRC", "")
    if python and src and Path(python).is_file() and Path(src).is_dir():
        return python, src
    return None


def _load():
    root = Path(__file__).resolve().parents[1]
    key = "recall_" + re.sub(r"\W", "_", root.name)
    spec = importlib.util.spec_from_file_location(
        key, root / "__init__.py", submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    ctx = _Ctx()
    module.register(ctx)
    return ctx.tools


def _measure():
    found = _hermes_paths()
    if found is None:
        print("MISSING_HERMES")
        return 0
    _python, src = found
    home = os.environ.get("HERMES_HOME", "")
    if not home:
        print("MISSING_HOME")
        return 1
    Path(home).mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, src)
    from toolsets import _HERMES_CORE_TOOLS
    import model_tools  # noqa: F401
    from tools.registry import registry
    from tools.tool_search_catalog import build_catalog, search_catalog

    tools = _load()
    core_names = set(_HERMES_CORE_TOOLS)
    core = []
    for entry in registry.get_all_entries():
        if entry.name in core_names:
            core.append({"type": "function", "function": {**entry.schema, "name": entry.name}})
    for tool in tools:
        registry.register(
            name=tool["name"], toolset=tool["toolset"] or "plugin", schema=tool["schema"],
            handler=lambda **_k: "", override=True)
    catalog = build_catalog(
        core + [{"type": "function", "function": tool["schema"]} for tool in tools])
    own = {tool["name"] for tool in tools}
    hits = 0
    for query in QUERIES:
        ranked = [item.name for item in search_catalog(catalog, query, limit=5)]
        ok = any(name in own for name in ranked)
        hits += int(ok)
        print(("HIT" if ok else "MISS"), query, ranked)
    print(f"{hits}/10")
    return hits


def test_ten_queries_in_top_five(tmp_path):
    import pytest

    found = _hermes_paths()
    if found is None:
        pytest.skip(
            "Set HERMES_AGENT_PYTHON and HERMES_AGENT_SRC to rank this plugin against Hermes core tools."
        )
    python, src = found
    env = os.environ.copy()
    env["HERMES_HOME"] = str(tmp_path / "empty-home")
    env["HERMES_AGENT_PYTHON"] = python
    env["HERMES_AGENT_SRC"] = src
    proc = subprocess.run(
        [python, str(Path(__file__).resolve())], capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "10/10"


if __name__ == "__main__":
    raise SystemExit(0 if _measure() == 10 else 1)
