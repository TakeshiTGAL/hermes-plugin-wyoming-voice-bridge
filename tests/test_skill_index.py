"""With default Tool Search, this plugin's skill is listed in the system prompt.

The model is not called. No network calls are made. Skip when HERMES_AGENT_PYTHON is unset.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _agent_python() -> Path | None:
    raw = os.environ.get("HERMES_AGENT_PYTHON", "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file():
        return path
    return None


def _skill_names(repo: Path) -> list[str]:
    plugin_name = ""
    for line in (repo / "plugin.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("name:"):
            plugin_name = line.split(":", 1)[1].strip().strip("\"'")
            break
    names = []
    for path in sorted((repo / "skills").glob("*/SKILL.md")):
        skill = path.parent.name
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("name:"):
                skill = line.split(":", 1)[1].strip().strip("\"'")
                break
        names.append(f"{plugin_name}:{skill}")
    return names


def _child() -> int:
    repo = Path(sys.argv[1]).resolve()
    expected = _skill_names(repo)
    if not expected:
        print("SKILL_INDEX_NONE")
        return 1
    scratch = Path(tempfile.mkdtemp(prefix="skill-index-"))
    home = scratch / "home"
    home.mkdir()
    tree = scratch / "tree"
    shutil.copytree(
        repo,
        tree,
        ignore=shutil.ignore_patterns(".git", ".pytest_cache", "__pycache__", "node_modules", ".venv", "*.pyc"),
    )
    git_env = dict(os.environ)
    git_env.update({
        "GIT_AUTHOR_NAME": "skill-index",
        "GIT_AUTHOR_EMAIL": "skill-index@example.com",
        "GIT_COMMITTER_NAME": "skill-index",
        "GIT_COMMITTER_EMAIL": "skill-index@example.com",
    })
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True, env=git_env)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True, env=git_env)
    subprocess.run(
        ["git", "-c", "user.name=skill-index", "-c", "user.email=skill-index@example.com",
         "commit", "-q", "-m", "skill index tree"],
        cwd=tree, check=True, env=git_env,
    )
    env = dict(git_env)
    env.update({
        "HERMES_HOME": str(home),
        "HERMES_DISABLE_UPDATE_CHECK": "1",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "",
    })
    # Clone the file tree into a temporary home and enable it in config.
    # Do not set tool_search, so the default auto mode stays in effect.
    plugin_name = expected[0].split(":", 1)[0]
    dest = home / "plugins" / plugin_name
    dest.parent.mkdir(parents=True)
    cloned = subprocess.run(
        ["git", "clone", "-q", tree.as_uri(), str(dest)],
        cwd="/tmp", env=env, capture_output=True, text=True,
    )
    if cloned.returncode != 0:
        print(cloned.stdout)
        print(cloned.stderr)
        print("SKILL_INDEX_INSTALL_FAIL")
        return cloned.returncode or 1
    (home / "config.yaml").write_text(
        f"plugins:\n  enabled:\n    - {plugin_name}\n",
        encoding="utf-8",
    )
    os.environ.update(env)
    os.chdir("/tmp")
    from run_agent import AIAgent
    from agent.system_prompt import build_system_prompt

    agent = AIAgent(
        base_url="http://127.0.0.1:9/v1", api_key="sk-fake-not-real", provider="custom",
        model="fake-model", quiet_mode=True, skip_memory=True, platform="cli",
        skip_context_files=True,
    )
    prompt = build_system_prompt(agent)
    start = prompt.find("<available_skills>")
    end = prompt.find("</available_skills>")
    block = prompt[start:end] if start != -1 and end != -1 else ""
    missing = [name for name in expected if name not in block]
    print(block)
    if missing:
        print("SKILL_INDEX_MISS", " ".join(missing))
        return 1
    print("SKILL_INDEX_HIT", " ".join(expected))
    return 0


def test_skill_is_listed_under_default_tool_search():
    import pytest

    python = _agent_python()
    if python is None:
        pytest.skip("Set HERMES_AGENT_PYTHON to build the system prompt skill list.")
    repo = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [str(python), str(Path(__file__).resolve()), str(repo), str(python)],
        capture_output=True, text=True, timeout=180,
    )
    tail = "\n".join((proc.stdout or "").splitlines()[-8:])
    assert proc.returncode == 0, tail + "\n" + (proc.stderr or "")[-800:]
    assert "SKILL_INDEX_HIT" in proc.stdout


if __name__ == "__main__":
    raise SystemExit(_child())
