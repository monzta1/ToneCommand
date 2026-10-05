from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_root_helper_uses_source_root():
    from fm9.paths import project_root, resource_path

    assert project_root() == ROOT
    assert resource_path("ui", "index.html") == ROOT / "ui" / "index.html"


def test_root_helper_uses_meipass(monkeypatch, tmp_path):
    import fm9.paths as paths

    monkeypatch.setattr(paths.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.project_root() == tmp_path
    assert paths.resource_path("config") == tmp_path / "config"


def test_spec_declares_required_data_and_native_collections():
    script = (ROOT / "packaging" / "build_macos.sh").read_text(encoding="utf-8")
    assert "TONECOMMAND_ENTRYPOINT" in script
    assert '"$ENTRYPOINT"' in script
    for resource in ("ui", "config", "recipes"):
        assert f"--add-data \"$ROOT/{resource}:{resource}\"" in script
    assert "--collect-all rtmidi" in script
    assert "--collect-all sounddevice" in script
    assert "--collect-submodules mido.backends" in script


def test_smoke_script_has_api_and_ui_probes():
    script = (ROOT / "packaging" / "smoke.py").read_text(encoding="utf-8")
    assert "/api/state" in script
    assert "http://127.0.0.1:{port}/" in script
    assert "TONECOMMAND_SIM" in script
    assert "SMOKE_OK" in script


def test_port_env_is_honoured(monkeypatch):
    import uvicorn
    import server

    called = {}
    monkeypatch.setattr(server.ai_settings, "apply_to_env", lambda: None)
    monkeypatch.setattr(server, "_pump_coremidi", lambda: None)
    monkeypatch.setattr(uvicorn, "run", lambda app, host, port: called.update(host=host, port=port))
    monkeypatch.setenv("TONECOMMAND_PORT", "8917")
    server.main()
    assert called == {"host": "127.0.0.1", "port": 8917}


def test_workflow_is_tag_or_manual_only():
    workflow = (ROOT / ".github" / "workflows" / "bundle.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "tags: [\"v*\"]" in workflow or "tags:\n" in workflow
    assert "macos-14" in workflow
    assert "ToneCommand-macOS-${{ steps.version.outputs.version }}.zip" in workflow


def test_docs_and_changelog_describe_unsigned_app():
    setup = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "macOS app (no Python)" in setup
    assert "not signed by an identified developer" in setup
    assert "## Unreleased" in changelog
    assert "ToneCommand.app" in changelog


# --- what a plain `pip install .` must be able to import (2026-09-20, #175's CI smoke) ----------

def _top_level_imports(paths):
    import ast
    names = set()
    for p in paths:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names.add(node.module.split(".")[0])
    return names


def test_every_repo_package_the_server_imports_is_packaged():
    import tomllib
    root = Path(__file__).resolve().parent.parent
    cfg = tomllib.load(open(root / "pyproject.toml", "rb"))
    packaged = set(cfg["tool"]["setuptools"]["packages"]) | set(cfg["tool"]["setuptools"].get("py-modules", []))
    sources = [root / "server.py", *sorted((root / "fm9").glob("*.py")), *sorted((root / "devices").rglob("*.py"))]
    local_dirs = {p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    needed = {n for n in _top_level_imports(sources) if n in local_dirs}
    missing = sorted(needed - packaged)
    assert not missing, f"imported by the app but not in [tool.setuptools] packages: {missing}"


def test_every_module_level_third_party_import_is_a_core_dependency():
    """A module the server imports unconditionally must not depend on an
    optional extra: numpy sat in `audition` while measure.py imported it at
    module level, and a plain install died on import."""
    import tomllib, sys, ast
    root = Path(__file__).resolve().parent.parent
    cfg = tomllib.load(open(root / "pyproject.toml", "rb"))
    core = {d.split(";")[0].split(">")[0].split("<")[0].split("[")[0].strip().lower().replace("-", "_")
            for d in cfg["project"]["dependencies"]}
    core |= {"rtmidi", "supriya_midi"}                       # python-rtmidi and supriya-midi import under these names
    stdlib = set(sys.stdlib_module_names)
    local_dirs = {p.name for p in root.iterdir() if p.is_dir()} | {"server"}
    # only imports at module level (not inside a function) count
    sources = [root / "server.py", *sorted((root / "fm9").glob("*.py"))]
    offenders = []
    for p in sources:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in tree.body:
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            for n in names:
                if n in stdlib or n in local_dirs or n.startswith("_"):
                    continue
                if n.lower().replace("-", "_") not in core:
                    offenders.append(f"{p.relative_to(root)}: {n}")
    assert not offenders, offenders


def test_every_repo_subpackage_the_app_imports_is_packaged():
    """#209: the top-level check above passed while devices.ir2 and
    devices.tonex were missing, because 'devices' was packaged. Every
    directory with an __init__.py under a packaged root is a subpackage the
    wheel must carry by name."""
    import tomllib
    cfg = tomllib.load(open(ROOT / "pyproject.toml", "rb"))
    packaged = set(cfg["tool"]["setuptools"]["packages"])
    needed = set()
    for top in ("fm9", "devices", "tools"):
        for init in (ROOT / top).rglob("__init__.py"):
            if "__pycache__" in init.parts:
                continue
            needed.add(".".join(init.parent.relative_to(ROOT).parts))
    missing = sorted(n for n in needed if n not in packaged)
    assert not missing, f"subpackages not in [tool.setuptools] packages: {missing}"


def test_the_device_catalog_ships_as_package_data():
    import tomllib
    cfg = tomllib.load(open(ROOT / "pyproject.toml", "rb"))
    assert "catalog.json" in cfg["tool"]["setuptools"]["package-data"]["devices"]
    assert (ROOT / "devices" / "catalog.json").is_file()
    # and it is read the installed way, through the package, not a repo path
    from devices import catalog
    assert "resources.files(\"devices\")" in (ROOT / "devices" / "catalog.py").read_text(encoding="utf-8")
    assert catalog.load()
