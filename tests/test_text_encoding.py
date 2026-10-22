"""Every text read and write names its encoding (#184).

A Windows install on Python 3.12 died on startup because
`Path.read_text()` uses the locale encoding, which is cp1252 there, and
`config/amp_models.json` carries curly quotes. Anything that reads or
writes text without saying which encoding behaves differently on the
user's machine than on ours, and CI (Linux, UTF-8 locale) can never see
it. These tests fail on a new encoding-less call and prove the shipped
data files load under a non-UTF-8 locale.
"""
from __future__ import annotations

import ast
import json
import locale
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".venv", "node_modules", "build", "dist", ".git", "__pycache__", "backups", "kb"}
#: `<owner>.open(...)` that is not a text file open and takes no encoding:
#: raw file descriptors, archive and audio containers, images, sockets, a
#: browser window, a websocket tab, a MIDI port. Everything else that ends
#: in `.open()` is treated as a path and must name its encoding.
NON_FILE_OPENS = {
    "os", "wave", "tarfile", "zipfile", "gzip", "bz2", "lzma", "Image",
    "webbrowser", "Tab", "socket", "sqlite3", "_opener", "opener",
    "SupriyaIn", "SupriyaOut", "mido", "rtmidi",
}


def _sources() -> list[Path]:
    return [p for p in ROOT.rglob("*.py") if not SKIP_PARTS & set(p.relative_to(ROOT).parts)]


def _binary(call: ast.Call) -> bool:
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) and isinstance(call.args[1].value, str):
        return "b" in call.args[1].value
    for keyword in call.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            return "b" in keyword.value.value
    return False


def _offenders(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        if any(keyword.arg == "encoding" for keyword in node.keywords) or _binary(node):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
        if name not in {"read_text", "write_text", "open"}:
            continue
        if name == "open" and isinstance(node.func, ast.Attribute):
            owner = (ast.get_source_segment(source, node.func.value) or "").split(".")[-1]
            if owner in NON_FILE_OPENS:
                continue
            found.append(f"{path.relative_to(ROOT)}:{node.lineno}: {owner}.open() without encoding")
            continue
        found.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}() without encoding")
    return found


def test_no_text_io_without_an_encoding():
    offenders = [item for path in _sources() for item in _offenders(path)]
    assert offenders == [], (
        "text I/O without an explicit encoding follows the machine's locale "
        "(cp1252 on Windows) and breaks on any non-ASCII byte:\n" + "\n".join(offenders)
    )


def test_every_shipped_data_file_is_utf_8_and_at_least_one_defeats_cp1252():
    """The repository is written in UTF-8, and the risk is not theoretical:
    at least one shipped file holds a byte cp1252 cannot decode at all
    (config/amp_models.json's curly quotes, the #184 crash)."""
    undecodable_under_cp1252 = []
    for path in sorted((ROOT / "config").rglob("*.json")):
        raw = path.read_bytes()
        json.loads(raw.decode("utf-8"))          # the encoding the repository is written in
        try:
            raw.decode("cp1252")
        except UnicodeDecodeError:
            undecodable_under_cp1252.append(path.name)
    assert "amp_models.json" in undecodable_under_cp1252, (
        "no shipped data file defeats cp1252 any more, so this guard proves nothing; "
        "keep it honest or delete it"
    )


def test_the_registry_loads_with_the_locale_encoding_forced_to_cp1252(monkeypatch):
    monkeypatch.setattr(locale, "getpreferredencoding", lambda *args, **kwargs: "cp1252")
    from fm9.registry import Registry

    registry = Registry()
    assert registry.amp_roster, "the amp roster is empty; the registry did not load"
