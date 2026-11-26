#!/usr/bin/env python3
"""See the UI the way Moncy sees it: drive a real browser, not the source.

WHY THIS EXISTS
---------------
Three UI complaints in a row (a preset box that resized, scene names
overflowing, a gear icon nobody could hit) were all things a single look at
the rendered page would have caught, and all three were shipped because the
agent had verified them by reading index.html. Reading CSS tells you what you
told the browser. It does not tell you what the browser did, and those differ
constantly: a font-size increase on U+2699 that moved nothing because the
glyph is drawn small inside its own em box, a grid item that would not shrink
below its own text so the ellipsis never fired.

So: never report a UI change as done on the strength of the diff. Render it.

WHAT IT DOES
------------
Runs headless Chrome with the DevTools protocol open, so this can both
screenshot the page and evaluate JavaScript inside it. Evaluation is the half
that matters for anything conditional: warnings, empty states, error paths and
modals cannot be photographed until something puts the page into that state,
and the honest way to do that is to run the app's own functions.

    tools/ui_probe.py shot out.png
    tools/ui_probe.py shot out.png --setup "gotoScene(3)"
    tools/ui_probe.py eval "JSON.stringify([...affectedScenes])"
    tools/ui_probe.py eval --file questions.json

Screenshots come back at deviceScaleFactor 2, because at 1x the antialiasing
on this theme's thin amber and violet borders is heavy enough to make a real
colour look like a rendering artefact and vice versa.

Chrome is left running between calls, and reused if it is already up, so a
sequence of probes does not pay browser startup each time. `--kill` stops it.

SAFETY
------
This drives the actual UI against the actual FM9. Evaluating gotoScene() or
clicking ENGAGE really does move the rig or spend a planner call. Nothing here
transmits by itself, but a --setup expression can, so read what you are about
to run. The one thing never to automate is $('apply').click(): TRANSMIT is the
confirm gate, and a gate a script can walk through is not a gate.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222
def _default_url() -> str:
    """#340: the opening link, so the probe's own browser holds the access key."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from fm9 import access
        return access.link(8909)
    except Exception:                     # noqa: BLE001  the plain address still reads
        return "http://127.0.0.1:8909/"


UI_URL = os.environ.get("TONECOMMAND_UI_URL") or _default_url()
PROFILE = Path(os.environ.get("TMPDIR", "/tmp")) / "tonecommand-ui-probe"


def _devtools(path: str = "/json"):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=2) as r:
        return json.load(r)


def chrome_up() -> bool:
    try:
        _devtools("/json/version")
        return True
    except (urllib.error.URLError, OSError):
        return False


def start_chrome(quiet: bool = False) -> None:
    """Reuse a running browser; a cold start costs about four seconds."""
    if chrome_up():
        return
    if not Path(CHROME).exists():
        sys.exit(f"Chrome not found at {CHROME}")
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [CHROME, "--headless", f"--remote-debugging-port={PORT}", "--disable-gpu",
         f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check",
         "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.25)
        if chrome_up():
            if not quiet:
                print("chrome up", file=sys.stderr)
            return
    sys.exit("chrome did not open a debugging port")


def kill_chrome() -> None:
    subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], check=False)
    shutil.rmtree(PROFILE, ignore_errors=True)
    print("chrome stopped")


class Tab:
    """The few DevTools calls this needs, over one websocket."""

    def __init__(self, ws):
        self.ws = ws
        self.n = 0

    @staticmethod
    async def open():
        import websockets                       # only needed for live probing
        tabs = [t for t in _devtools() if t["type"] == "page"]
        if not tabs:
            sys.exit("no page target in chrome")
        # ping_interval=None because the operations worth probing are the slow
        # ones. A health scan walks eight scenes and takes the better part of a
        # minute, and the library's 20s keepalive killed the connection
        # mid-scan: the rig did the work, the probe never saw the result.
        return websockets.connect(tabs[0]["webSocketDebuggerUrl"],
                                  max_size=64 << 20, ping_interval=None)

    async def send(self, method: str, **params):
        self.n += 1
        await self.ws.send(json.dumps({"id": self.n, "method": method,
                                       "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    sys.exit(f"{method}: {msg['error'].get('message')}")
                return msg.get("result", {})

    async def goto(self, url: str, settle: float, width: int, height: int):
        await self.send("Page.enable")
        await self.send("Runtime.enable")
        # Without this the browser can serve index.html from its own cache and
        # the probe reports on a page that no longer exists on disk. A tool
        # whose entire purpose is to show what is really rendered must never
        # be one edit behind: it turns "I checked" into a false statement.
        await self.send("Network.enable")
        await self.send("Network.setCacheDisabled", cacheDisabled=True)
        await self.send("Emulation.setDeviceMetricsOverride", width=width,
                        height=height, deviceScaleFactor=2, mobile=False)
        await self.send("Page.navigate", url=url)
        # The page polls the FM9 on an interval, so the first paint is empty
        # panels. Waiting is not politeness, it is the difference between
        # photographing the UI and photographing "awaiting link...".
        await asyncio.sleep(settle)

    async def js(self, expression: str):
        r = await self.send("Runtime.evaluate", expression=expression,
                            returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            return {"error": (d.get("exception", {}).get("description")
                              or d.get("text", "evaluation failed"))}
        return {"value": r.get("result", {}).get("value")}


async def _run(args) -> int:
    conn = await Tab.open()
    async with conn as ws:
        tab = Tab(ws)
        await tab.goto(args.url, args.settle, args.width, args.height)
        if args.setup:
            out = await tab.js(args.setup)
            if "error" in out:
                print(f"setup failed: {out['error']}", file=sys.stderr)
                return 1
            await asyncio.sleep(args.after_setup)

        if args.cmd == "eval":
            probes = (json.loads(Path(args.file).read_text(encoding="utf-8")) if args.file
                      else [["result", args.expression]])
            bad = 0
            for label, expr in probes:
                out = await tab.js(expr)
                if "error" in out:
                    bad = 1
                    print(f"--- {label}\n    ERROR {out['error'][:400]}")
                else:
                    print(f"--- {label}\n    "
                          + json.dumps(out["value"], indent=2)[:4000])
            return bad

        shot = await tab.send("Page.captureScreenshot", format="png",
                              captureBeyondViewport=args.full)
        Path(args.out).write_bytes(base64.b64decode(shot["data"]))
        print(args.out)
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default=UI_URL)
    ap.add_argument("--settle", type=float, default=4.0,
                    help="seconds to let the first FM9 poll land (default 4)")
    ap.add_argument("--after-setup", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--setup", help="JS to run before looking, e.g. \"gotoScene(3)\"")
    ap.add_argument("--kill", action="store_true", help="stop the browser and exit")
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("shot", help="screenshot the page")
    s.add_argument("out")
    s.add_argument("--full", action="store_true", help="whole page, not just the viewport")

    e = sub.add_parser("eval", help="run JS inside the page and print what it returns")
    e.add_argument("expression", nargs="?")
    e.add_argument("--file", help='JSON [["label", "expr"], ...]')

    args = ap.parse_args()
    if args.kill:
        kill_chrome()
        return 0
    if not args.cmd:
        ap.print_help()
        return 2
    if args.cmd == "eval" and not (args.expression or args.file):
        ap.error("eval needs an expression or --file")
    start_chrome()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
