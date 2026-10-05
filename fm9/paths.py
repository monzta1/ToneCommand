"""Paths for resources that live beside the source or inside a frozen app."""
from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    """Return the source root, or PyInstaller's extracted application root."""
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        return Path(frozen)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolve a bundled or source-tree resource by its repository-relative path."""
    return project_root().joinpath(*parts)


#: The one line a plain `pip install .` gets (#177). The wheel carries the
#: code but not config/, ui/ or recipes/, and the app also writes its own
#: state beside the code, which inside site-packages is the wrong place.
#: Making that install work is #208's packaging phase; until then it is
#: refused in words rather than crashing on a missing catalog.
UNSUPPORTED_INSTALL = (
    "ToneCommand runs from a checkout (git clone, then pip install -e .) or "
    "the bundled app; a plain 'pip install .' does not carry its data yet "
    "(#177). See docs/SETUP.md.")


def install_kind(root: Path | None = None) -> str:
    """'frozen' (the bundled app), 'checkout' (a source tree, which the
    editable install runs from) or 'wheel' (anything else)."""
    if getattr(sys, "_MEIPASS", None):
        return "frozen"
    root = Path(root) if root is not None else project_root()
    if (root / "pyproject.toml").is_file() and (root / "ui" / "index.html").is_file():
        return "checkout"
    return "wheel"


def require_supported_install(root: Path | None = None) -> None:
    """Refuse an install that cannot work, with the one line that says what
    does, before anything reads a data file that is not there."""
    if install_kind(root) == "wheel":
        raise SystemExit(UNSUPPORTED_INSTALL)
