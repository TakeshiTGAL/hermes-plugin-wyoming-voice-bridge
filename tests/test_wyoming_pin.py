"""The installed wyoming tree is imported only when its sha256 is listed."""
import importlib.metadata
import importlib.util
import shutil
from pathlib import Path

import pytest

from messages import library_missing, library_unpinned
from session import BridgeError
from wyoming_pin import (
    SHIPPED_WYOMING_SHA256,
    WYOMING_1_5_4_TREE_SHA256,
    WYOMING_SHA256,
    library_status,
    tree_digest,
)


def test_table_lists_only_the_declared_wyoming_1_5_4_tree():
    assert WYOMING_1_5_4_TREE_SHA256 == "d3fd5dcc24ad89a5145de41dbd1e7ac2b6597d67cc610fd19c32368d1132e8c6"
    assert SHIPPED_WYOMING_SHA256 == frozenset({WYOMING_1_5_4_TREE_SHA256})
    assert WYOMING_SHA256 is SHIPPED_WYOMING_SHA256
    manifest = (Path(__file__).resolve().parents[1] / "plugin.yaml").read_text(encoding="utf-8")
    assert '"wyoming==1.5.4"' in manifest


def _installed_root() -> Path:
    spec = importlib.util.find_spec("wyoming")
    if spec is None or not spec.origin:
        pytest.skip("wyoming is not installed in this Python")
    return Path(spec.origin).parent


def test_installed_wyoming_is_the_listed_tree():
    root = _installed_root()
    version = importlib.metadata.version("wyoming")
    assert version == "1.5.4", (
        f"wyoming {version} is installed. plugin.yaml declares 1.5.4, and only that tree is imported."
    )
    assert tree_digest(root) == WYOMING_1_5_4_TREE_SHA256
    assert library_status() == "ready"


def test_a_copy_matches_and_one_changed_byte_does_not(tmp_path, monkeypatch):
    root = _installed_root()
    if tree_digest(root) != WYOMING_1_5_4_TREE_SHA256:
        pytest.fail("the installed wyoming tree is not the listed 1.5.4 tree")
    copy = tmp_path / "wyoming"
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    monkeypatch.setattr("wyoming_pin._origin_root", lambda: copy)
    assert library_status() == "ready"
    target = copy / "__init__.py"
    target.write_bytes(target.read_bytes() + b"\n")
    assert library_status() == "unpinned"


def test_unlisted_tree_is_not_ready(tmp_path, monkeypatch):
    package = tmp_path / "wyoming"
    package.mkdir()
    (package / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr("wyoming_pin._origin_root", lambda: package)
    assert library_status() == "unpinned"
    monkeypatch.setattr("wyoming_pin.WYOMING_SHA256", frozenset({tree_digest(package)}))
    assert library_status() == "ready"


def test_a_symlink_inside_the_tree_is_not_a_digest(tmp_path):
    package = tmp_path / "wyoming"
    package.mkdir()
    (package / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    target = tmp_path / "other.py"
    target.write_text("y = 2\n", encoding="utf-8")
    (package / "extra.py").symlink_to(target)
    assert tree_digest(package) is None


def test_missing_package_is_not_imported(monkeypatch):
    monkeypatch.setattr("wyoming_pin._origin_root", lambda: None)
    from service import _library_ready

    try:
        _library_ready()
    except BridgeError as caught:
        assert caught.message == library_missing()
    else:
        raise AssertionError("missing wyoming was imported")


def test_unpinned_package_is_not_imported(tmp_path, monkeypatch):
    package = tmp_path / "wyoming"
    package.mkdir()
    (package / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr("wyoming_pin._origin_root", lambda: package)
    monkeypatch.setattr("wyoming_pin.WYOMING_SHA256", frozenset())
    from service import _library_ready

    try:
        _library_ready()
    except BridgeError as caught:
        assert caught.message == library_unpinned()
    else:
        raise AssertionError("unpinned wyoming was imported")
    assert Path(package / "__init__.py").is_file()
