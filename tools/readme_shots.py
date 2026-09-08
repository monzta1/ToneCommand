"""Re-take the README screenshots from the LIVE app on the connected FM9.

    .venv/bin/python tools/readme_shots.py            # writes docs/img/*.png
    .venv/bin/python tools/readme_shots.py --out DIR  # somewhere else first

Nothing here writes to the rig. The blast-radius shot drives a one-action
plan into the page locally (shown, never sent); the health scan and the
shared-channel sweep are the tool's own read-only operations, which step the
rig audibly through the scenes and put it back. Each capture is the browser
at 2x, cropped to the panel, then sized and quantised to 256 colours the way
the README shots have always been (a dark UI with two accent hues loses
nothing visible and a megabyte becomes a couple of hundred kilobytes).

Needs the server running on 127.0.0.1:8909 against a real, connected FM9:
the README promises every screenshot is live from one, so this refuses the
simulator.

The graphic EQ panel only renders when the loaded preset has an EQ block; if
it does not, that shot is skipped and said so, because switching presets
discards the edit buffer and is the owner's call.
"""
import argparse
import asyncio
import base64
import io
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_probe  # noqa: E402

from PIL import Image  # noqa: E402

URL = "http://127.0.0.1:8909/"
#: A request the README itself quotes. It goes through whatever planner the
#: app is set to, so it costs whatever that planner costs (a subscription
#: backend costs nothing per call; an API-key backend costs cents).
REQUEST = "a Klon into a JCM800 with a greenback 4x12"
ROOT = Path(__file__).resolve().parent.parent
SIZES = {"ui-full": 2000, "audition-amp": 1800, "audition-cab": 1800, "graphic-eq": 1800,
         "pedal-and-bypass": 1800, "blast-radius": 1800, "health-scan": 1200}


def state() -> dict:
    with urllib.request.urlopen(URL + "api/state", timeout=5) as r:
        return json.load(r)


def finish(img: Image.Image, name: str, out: Path) -> None:
    width = SIZES.get(name, 1800)
    img = img.convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    q = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
    q.save(out / f"{name}.png", optimize=True)
    print(f"{name}.png: {q.width}x{q.height}, {(out / f'{name}.png').stat().st_size // 1024} KB")


async def run(out: Path, empty: bool) -> int:
    ui_probe.start_chrome(quiet=True)
    conn = await ui_probe.Tab.open()
    async with conn as ws:
        tab = ui_probe.Tab(ws)

        async def js(expr):
            r = await tab.js(expr)
            if "error" in r:
                raise RuntimeError(r["error"])
            return r["value"]

        async def rect(sel, page):
            return json.loads(await js(
                f"(() => {{ const r = document.querySelector({json.dumps(sel)}).getBoundingClientRect();"
                f" const sx = {'window.scrollX' if page else '0'}, sy = {'window.scrollY' if page else '0'};"
                f" return JSON.stringify({{l: r.left + sx, t: r.top + sy, r: r.right + sx, b: r.bottom + sy}}); }})()"))

        async def grab(selectors, page, pad=10) -> Image.Image:
            shot = await tab.send("Page.captureScreenshot", format="png", captureBeyondViewport=page)
            img = Image.open(io.BytesIO(base64.b64decode(shot["data"])))
            rs = [await rect(s, page) for s in selectors]
            box = (min(r["l"] for r in rs) - pad, min(r["t"] for r in rs) - pad,
                   max(r["r"] for r in rs) + pad, max(r["b"] for r in rs) + pad)
            return img.crop(tuple(max(0, int(v * 2)) for v in box))

        async def fresh(width=1512, height=982, settle=3.0):
            await tab.goto(URL, settle, width, height)

        async def inspector_scroll_to(panel_id):
            await js(f"(() => {{ const ins = document.getElementById('inspector');"
                     f" const head = ins.querySelector('.insphead'); const p = document.getElementById({json.dumps(panel_id)});"
                     f" ins.scrollTop = p.offsetTop - head.offsetHeight - 6; return 1; }})()")
            await asyncio.sleep(0.6)

        before = state()
        print("rig:", before["preset"]["label"], before["preset"]["name"], "scene", before["scene"]["number"])

        # the whole page, at the PLAN stage of a real request through the real
        # planner: proposed, never sent. --empty takes the idle page instead.
        await fresh()
        if not empty:
            await js("(() => { const p = document.getElementById('prompt'); p.value = "
                     + json.dumps(REQUEST) + "; p.dispatchEvent(new Event('input', {bubbles: true}));"
                     " submitRequest(); return 1; })()")
            for _ in range(300):
                await asyncio.sleep(1)
                st = json.loads(await js("JSON.stringify({plan: !document.getElementById('pane-plan').hidden,"
                                         " cards: document.querySelectorAll('#plancards > *').length,"
                                         " ask: typeof chatNeedsAnswer !== 'undefined' && chatNeedsAnswer})"))
                if st["plan"] and st["cards"]:
                    break
                if st["ask"]:
                    print("the planner asked a question instead of planning; taking the idle page", file=sys.stderr)
                    await fresh()
                    break
            else:
                print("no plan within five minutes; taking the idle page", file=sys.stderr)
                await fresh()
            await asyncio.sleep(2.0)
            await js("window.scrollTo(0, 0)")
        finish(await grab(["body"], False, pad=0), "ui-full", out)
        await js("typeof discardPlan === 'function' && discardPlan()")

        # auditions: the popover is position:fixed, so capture the viewport
        for kind, filt in (("amp", None), ("cab", "v30")):
            await fresh(1512, 1400)
            await js("openManual()"); await asyncio.sleep(1.2)
            await inspector_scroll_to("amppanel")
            await js(f"audOpenFrom(document.querySelector('[data-aud=\"{kind}\"]'))"); await asyncio.sleep(1.5)
            if filt:
                await js(f"(() => {{ const i = document.querySelector('#audpop input'); i.value = {json.dumps(filt)};"
                         f" i.dispatchEvent(new Event('input', {{bubbles: true}})); return 1; }})()")
                await asyncio.sleep(1.2)
            finish(await grab(["#inspector .insphead", "#amppanel", "#audpop"], False), f"audition-{kind}", out)

        # graphic EQ, only when this preset has one
        await fresh(1512, 1400)
        await js("openManual()"); await asyncio.sleep(1.0)
        if await js("getComputedStyle(document.getElementById('geqpanel')).display") != "none":
            await js("selectBlock('GEQ')"); await asyncio.sleep(0.8)
            await inspector_scroll_to("geqpanel")
            finish(await grab(["#inspector .insphead", "#geqpanel"], False), "graphic-eq", out)
        else:
            print("graphic-eq.png: SKIPPED, the loaded preset has no EQ block (load one that does and rerun)")

        # effects: bypass badges, modifier badges, and the P2 buttons shown (they appear on hover)
        await fresh(1512, 1400)
        await js("openManual()"); await asyncio.sleep(1.0)
        await js("selectBlock('CHORUS')"); await asyncio.sleep(0.8)
        await js("(() => { const s = document.createElement('style'); s.textContent = '.pedalbtn{opacity:1 !important}';"
                 " document.head.appendChild(s); return 1; })()")
        await inspector_scroll_to("fxpanel")
        finish(await grab(["#inspector .insphead", "#fxpanel"], False), "pedal-and-bypass", out)

        # health scan: a real scan, audible, restores the scene
        await fresh()
        await js("openDrawer('diagnostics')"); await asyncio.sleep(0.8)
        await js("scanPreset()")
        for _ in range(120):
            await asyncio.sleep(1)
            t = await js("document.getElementById('scan').textContent")
            if t != "SCANNING..." and not t.startswith("SCENE"):
                break
        await asyncio.sleep(1.0)
        finish(await grab(["#drawer"], True), "health-scan", out)

        # blast radius: the shared-channel map plus a local one-action plan, shown never sent
        await fresh()
        await js("ensureShared()")
        st = state()
        amp = next(b for b in st["blocks"] if b["family"] == "DISTORT")
        plan = {"summary": "Raise the amp mid a little for more cut on the lead.",
                "actions": [{"kind": "set_param", "block": "amp", "instance": 1, "param": "DISTORT_MID",
                             "value": 7.0, "effect_id": amp["effect_id"],
                             "reason": "a channel-level change: every scene on this amp channel moves with it"}]}
        await js(f"showPlan({json.dumps(plan)})"); await asyncio.sleep(1.5)
        await js("window.scrollTo(0, 0)"); await asyncio.sleep(0.5)
        rail = await grab(["#scenes"], True)
        card = await grab(["#blastcard"], True)
        pad = 28
        composed = Image.new("RGB", (rail.width, rail.height + pad + card.height + pad), (7, 10, 14))
        composed.paste(rail, (0, 0)); composed.paste(card, (24, rail.height + pad))
        finish(composed, "blast-radius", out)
        await js("discardPlan && discardPlan()")

        after = state()
        print("rig:", after["preset"]["label"], after["preset"]["name"], "scene", after["scene"]["number"])
        if (after["preset"]["number"], after["scene"]["number"]) != (before["preset"]["number"], before["scene"]["number"]):
            print("WARNING: the rig did not come back to where it started", file=sys.stderr)
            return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs" / "img"))
    ap.add_argument("--empty", action="store_true",
                    help="full-page shot of the idle page, without running the planner")
    args = ap.parse_args()
    try:
        st = state()
    except Exception as e:  # noqa: BLE001
        sys.exit(f"the server is not answering on {URL}: {e}")
    if not st.get("connected"):
        sys.exit("no FM9 connected: the README promises live screenshots, not simulator ones")
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    return asyncio.run(run(out, args.empty))


if __name__ == "__main__":
    sys.exit(main())
