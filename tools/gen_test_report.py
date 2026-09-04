#!/usr/bin/env python3
"""Generate a test report from a REAL suite run, not hand-typed numbers.

The point is honesty: the report a human reads must be produced by actually
running pytest, so it cannot drift from the truth. This runs the suite with
`--junitxml`, parses the machine-readable result, and renders an HTML page
whose every number comes from that run. If the suite is red, the page is red.

Usage:
    python tools/gen_test_report.py [OUTPUT_DIR]

OUTPUT_DIR defaults to ~/Projects/misc/tonecommand-tests/ (local, offline, not
committed). The page is written as index.html there, with the raw junit.xml
beside it so the numbers can be checked against the source.
"""
from __future__ import annotations

import html
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_suite(junit_path: Path) -> int:
    """Run the whole suite, writing junit XML. Returns pytest's exit code."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         f"--junitxml={junit_path}"],
        cwd=REPO, capture_output=True, text=True)
    sys.stdout.write(proc.stdout[-2000:])
    sys.stderr.write(proc.stderr[-2000:])
    return proc.returncode


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              cwd=REPO, capture_output=True, text=True
                              ).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def parse(junit_path: Path) -> dict:
    root = ET.parse(junit_path).getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    total = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    duration = float(suite.get("time", 0.0))
    files: dict[str, dict] = {}
    for case in suite.iter("testcase"):
        f = case.get("file") or case.get("classname", "").replace(".", "/") + ".py"
        rec = files.setdefault(f, {"pass": 0, "fail": 0, "skip": 0})
        if case.find("failure") is not None or case.find("error") is not None:
            rec["fail"] += 1
        elif case.find("skipped") is not None:
            rec["skip"] += 1
        else:
            rec["pass"] += 1
    passed = total - failures - errors - skipped
    return {"total": total, "passed": passed, "failing": failures + errors,
            "skipped": skipped, "duration": duration,
            "files": dict(sorted(files.items()))}


def short(path: str) -> str:
    p = path.replace("tests/", "").replace(".py", "")
    return p[5:] if p.startswith("test_") else p


def render(data: dict) -> str:
    green = data["failing"] == 0
    sha = git_sha()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    status = "ALL GREEN" if green else f"{data['failing']} FAILING"
    accent = "#12915b" if green else "#c0392b"
    rows = "".join(
        f'<tr><td class="f">{html.escape(short(f))}</td>'
        f'<td class="n ok">{r["pass"]}</td>'
        f'<td class="n {"bad" if r["fail"] else "dim"}">{r["fail"]}</td>'
        f'<td class="n dim">{r["skip"] or ""}</td></tr>'
        for f, r in data["files"].items())
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ToneCommand Tests</title>
<style>
  :root {{ color-scheme: light dark;
    --bg:#f6f8f8; --card:#fff; --line:#dce4e5; --text:#16201f; --muted:#5d6b6e;
    --accent:{accent}; --ok:#12915b; --bad:#c0392b; }}
  @media (prefers-color-scheme:dark){{ :root{{
    --bg:#0d1214; --card:#151d20; --line:#26343a; --text:#e6eef0; --muted:#93a3a8; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",sans-serif; }}
  .wrap {{ max-width:820px; margin:0 auto; padding:32px 20px 60px; }}
  h1 {{ font-size:20px; margin:0 0 2px; letter-spacing:-.01em; }}
  .sub {{ color:var(--muted); font-size:13px; margin:0 0 24px; }}
  .banner {{ display:flex; align-items:center; gap:12px; background:var(--card);
    border:1px solid var(--line); border-left:4px solid var(--accent);
    border-radius:10px; padding:16px 18px; margin-bottom:20px; }}
  .banner .dot {{ width:11px; height:11px; border-radius:50%; background:var(--accent); }}
  .banner b {{ font-size:16px; }}
  .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:24px; }}
  .m {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .m .v {{ font-size:26px; font-weight:700; font-variant-numeric:tabular-nums; }}
  .m .k {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
  th,td {{ text-align:left; padding:8px 14px; border-bottom:1px solid var(--line); }}
  th {{ font-size:11px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }}
  tr:last-child td {{ border-bottom:none; }}
  td.n {{ text-align:right; font-variant-numeric:tabular-nums; width:64px; }}
  td.f {{ font-family:ui-monospace,Menlo,monospace; font-size:13px; }}
  .ok {{ color:var(--ok); }} .bad {{ color:var(--bad); font-weight:700; }}
  .dim {{ color:var(--muted); }}
  footer {{ color:var(--muted); font-size:12px; margin-top:20px;
    font-family:ui-monospace,Menlo,monospace; }}
</style></head><body><div class="wrap">
  <h1>ToneCommand test report</h1>
  <p class="sub">Generated from a real pytest run &middot; {now} &middot; main @ {sha}</p>
  <div class="banner"><span class="dot"></span>
    <b>{status}</b>
    <span class="dim">&mdash; {data['passed']} passed of {data['total']} in {data['duration']:.0f}s</span>
  </div>
  <div class="metrics">
    <div class="m"><div class="v">{data['total']}</div><div class="k">Tests</div></div>
    <div class="m"><div class="v ok">{data['passed']}</div><div class="k">Passed</div></div>
    <div class="m"><div class="v {'bad' if data['failing'] else 'dim'}">{data['failing']}</div><div class="k">Failing</div></div>
    <div class="m"><div class="v">{len(data['files'])}</div><div class="k">Suites</div></div>
  </div>
  <table>
    <thead><tr><th>Suite</th><th class="n">Pass</th><th class="n">Fail</th><th class="n">Skip</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
  <footer>Reproduce: python tools/gen_test_report.py &middot; source junit.xml is beside this file</footer>
</div></body></html>"""


def main() -> int:
    out_dir = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else \
        Path.home() / "Projects" / "misc" / "tonecommand-tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    junit = out_dir / "junit.xml"
    print(f"running the suite -> {junit}")
    code = run_suite(junit)
    if not junit.exists():
        print("no junit produced; suite did not run", file=sys.stderr)
        return 1
    data = parse(junit)
    (out_dir / "index.html").write_text(render(data), encoding="utf-8")
    print(f"\nreport: {out_dir / 'index.html'}")
    print(f"  {data['passed']} passed, {data['failing']} failing, "
          f"{data['skipped']} skipped, {len(data['files'])} suites")
    # Exit non-zero if the suite was red, so this can gate too.
    return 0 if data["failing"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
