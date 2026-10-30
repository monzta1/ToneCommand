"""Opt-in handling of measured Axe-Edit information dialogs, not hardware IO.

This developer comparison helper never launches Axe-Edit, owns MIDI, presses
Save, or accepts an overwrite. Unknown dialogs stop the operation. pywinauto
is an optional Windows developer dependency, not an application requirement.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time


AXE_EDIT_PATH = Path(r"C:\Program Files\Fractal Audio\Axe-Edit III\Axe-Edit III.exe")
NAM_INFORMATION = (
    "This tool allows you to cut/copy/paste, drag-and-drop, swap, import/export, "
    "clear, rename, audition and more. Making backups with Fractal-Bot is "
    "recommended before working with critical data."
)
# The measured UIA content contains a duplicated 'to'; the visible version
# shown by another editor build does not. No substring or generic OK matching.
NAM_INFORMATION_UIA = NAM_INFORMATION.replace("you to cut", "you to to cut")


@dataclass(frozen=True)
class Dialog:
    handle: int
    title: str
    texts: tuple[tuple[str, str], ...]
    buttons: tuple[tuple[str, str, bool], ...]


def classify(dialog: Dialog) -> str:
    text = tuple((aid, " ".join(value.split())) for aid, value in dialog.texts)
    if (dialog.title == "Manage NAM"
            and text in ((("ContentText", NAM_INFORMATION),),
                         (("ContentText", NAM_INFORMATION_UIA),))
            and dialog.buttons == (("CommandButton_0", "OK", True),)):
        return "nam-manager-information"
    return "unknown"


class DialogBlocked(RuntimeError):
    """No UI action was authorized or the UI changed before confirmation."""


def handle_information(read, acknowledge, *, permit=False, timeout=3, clock=time.monotonic,
                       pause=time.sleep):
    """Inspect first, recheck before invoking, then verify the modal is gone.

    Callers must not continue their comparison after DialogBlocked. 'permit'
    allows only this informational acknowledgement, not any preset action.
    """
    initial = tuple(read())
    if not initial:
        return {"status": "clear", "acknowledged": False}
    if len(initial) != 1 or classify(initial[0]) == "unknown":
        raise DialogBlocked("Unknown or multiple dialogs; nothing acknowledged")
    if not permit:
        return {"status": "known-information", "acknowledged": False}
    if tuple(read()) != initial:
        raise DialogBlocked("Dialog changed before acknowledgement; nothing clicked")
    acknowledge(initial[0])
    deadline = clock() + timeout
    while True:
        remaining = tuple(read())
        if not remaining:
            return {"status": "clear", "acknowledged": True}
        if remaining != initial:
            raise DialogBlocked("A different dialog appeared; stopped without accepting it")
        if clock() >= deadline:
            raise DialogBlocked("Information dialog did not close; no repeat acknowledgement")
        pause(0.1)


def process_path(pid: int) -> Path:
    """Read the Windows executable identity before attaching to its UI."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = (
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        name = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(name))
        if not kernel.QueryFullProcessImageNameW(handle, 0, name, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return Path(name.value)
    finally:
        kernel.CloseHandle(handle)


class EditorDialogs:
    """Attach only to an already running, verified editor; never use hotkeys."""

    def __init__(self, pid):
        if os.name != "nt" or pid <= 0:
            raise ValueError("A positive existing Windows Axe-Edit PID is required")
        self.pid = pid
        self._identity()
        from pywinauto import Application
        self.window = Application(backend="uia").connect(process=pid).window(
            title="Axe-Edit III", auto_id="Axe-Edit III").wrapper_object()

    def _identity(self):
        if process_path(self.pid) != AXE_EDIT_PATH:
            raise DialogBlocked("Not the measured Axe-Edit executable; no UI action")

    def _windows(self):
        self._identity()
        return [w for w in self.window.descendants(control_type="Window") if w.is_visible()]

    @staticmethod
    def _snapshot(window):
        texts = tuple((x.element_info.automation_id, x.window_text())
                      for x in window.descendants(control_type="Text") if x.is_visible())
        buttons = tuple((x.element_info.automation_id, x.window_text(), x.is_enabled())
                        for x in window.descendants(control_type="Button") if x.is_visible())
        return Dialog(window.handle, window.window_text(), texts, buttons)

    def read(self):
        return tuple(self._snapshot(w) for w in self._windows())

    @staticmethod
    def _foreground_handle():
        import ctypes
        from ctypes import wintypes
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.GetForegroundWindow.restype = wintypes.HWND
        return user.GetForegroundWindow()

    def acknowledge(self, expected):
        windows = self._windows()
        if (len(windows) != 1 or self._snapshot(windows[0]) != expected
                or classify(expected) != "nam-manager-information"):
            raise DialogBlocked("Last-moment dialog mismatch; no UI action")
        windows[0].set_focus()
        if (self._foreground_handle() != expected.handle
                or self.read() != (expected,)):
            raise DialogBlocked("Modal is not the unchanged foreground window; no click")
        buttons = [b for b in windows[0].descendants(control_type="Button") if b.is_visible()]
        # This editor's native popup did not respond to UIA Invoke. Use the
        # measured foreground modal control, never a cached screen coordinate.
        buttons[0].click_input()

    def evidence(self, directory, report):
        """Local screenshot and status only; do not log unknown message bodies."""
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        image = directory / f"axe-edit-dialog-{stamp}.png"
        self.window.capture_as_image().save(image)
        status = directory / f"axe-edit-dialog-{stamp}.json"
        payload = {**report, "timestamp_utc": stamp, "preset_actions": False,
                   "midi_opened": False, "screenshot": str(image)}
        with status.open("x", encoding="utf-8") as out:
            json.dump(payload, out, indent=2)
        return str(status)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--ack-known-information", action="store_true")
    args = parser.parse_args(argv)
    editor = EditorDialogs(args.pid)
    before = editor.read()
    report = {"observed": [classify(d) for d in before]}
    try:
        report.update(handle_information(editor.read, editor.acknowledge,
                                         permit=args.ack_known_information))
    except DialogBlocked as exc:
        report.update(status="blocked", reason=str(exc))
    directory = Path(__file__).resolve().parents[1] / "backups" / "axe-edit-dialogs"
    artifact = editor.evidence(directory, report)
    print(json.dumps({**report, "evidence": artifact}))
    return 2 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
