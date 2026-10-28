"""Refuse to import wyoming unless this build's table lists the installed tree.

The table lists the tree of the official wyoming 1.5.4 wheel. A missing package,
a symlink, or a digest that is not listed is not imported. This module does not
import wyoming.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

# sha256 hex of the installed wyoming package tree (sorted relative paths and bytes).
# __pycache__ and .pyc files are skipped, so compiled bytecode does not change it.
# A tree whose digest is not listed is not imported.
# wyoming 1.5.4: wyoming-1.5.4-py3-none-any.whl from PyPI, whose file sha256 is
# cb044b8d9e0f625907efb1bde32cc38eaef67fdd495075f6127d98d3b12c0683 (the PyPI JSON value).
# The extracted wheel, pip 21.2.4 (Python 3.9), and uv (Python 3.12.14) all give this
# one tree value. README "Speech" has the steps.
WYOMING_1_5_4_TREE_SHA256 = "d3fd5dcc24ad89a5145de41dbd1e7ac2b6597d67cc610fd19c32368d1132e8c6"
SHIPPED_WYOMING_SHA256: frozenset[str] = frozenset({WYOMING_1_5_4_TREE_SHA256})
WYOMING_SHA256: frozenset[str] = SHIPPED_WYOMING_SHA256


def _origin_root() -> Path | None:
    try:
        spec = importlib.util.find_spec("wyoming")
    except Exception:
        return None
    if spec is None or not spec.origin or spec.origin in {"namespace", "built-in"}:
        return None
    origin = Path(spec.origin)
    try:
        if origin.is_symlink():
            return None
        root = origin.parent
        if root.is_symlink() or not root.is_dir():
            return None
    except OSError:
        return None
    return root


def tree_digest(root: Path) -> str | None:
    """Hash regular files under root. A symlink anywhere in the tree is refused."""
    digest = hashlib.sha256()
    try:
        files: list[Path] = []
        for path in root.rglob("*"):
            if path.is_symlink():
                return None
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            files.append(path)
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()


def installed_digest() -> str | None:
    root = _origin_root()
    if root is None:
        return None
    return tree_digest(root)


def library_status() -> str:
    """missing, unpinned, or ready. Does not import wyoming."""
    root = _origin_root()
    if root is None:
        return "missing"
    digest = tree_digest(root)
    if not digest or digest not in WYOMING_SHA256:
        return "unpinned"
    return "ready"
