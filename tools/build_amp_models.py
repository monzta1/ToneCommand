#!/usr/bin/env python3
"""Generate config/amp_models.json from the Amplifier Library Guide XML.

The FM9 amp roster in config/fm9_catalog.json gives Fractal's own names
("Brit 800 2204 High"). It does not say what real amp each one models. This
script joins the roster to the Amplifier Library Guide, which does, and writes
the result to a sidecar so the vendored catalog stays untouched.

Structure of the source (an InDesign/Acrobat XML export):

  * A table of contents of 331 <Link> entries, "NNN  TITLE  PAGE". This is the
    authoritative title list -- the in-body headings are split mid-word by
    figure boxes and sometimes absorb text from overlapping settings tables.
  * One block per amp, normally <Amp_Title> followed by <LBody> bullets, but
    twice (guide 020 and 285) an <Amp_Details> block holding its bullets
    inline, separated by the bullet glyph "g".

Usage:
    .venv/bin/python tools/build_amp_models.py                # everything
    .venv/bin/python tools/build_amp_models.py --facts-only   # specs, no prose

Re-run after a catalog refresh; the load-time check in fm9/registry.py will
tell you if the roster moved out from under this file.
"""
from __future__ import annotations

import argparse
import bisect
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "config" / "fm9_catalog.json"
OUT = ROOT / "config" / "amp_models.json"
DEFAULT_XML = Path.home() / "Downloads/FractalAmpGuides/Amplifier Library Guide.xml"

SCHEMA_VERSION = 2
EXPECTED_ENTRIES = 331

# The default build carries everything the guide gives per amp, prose included.
# --facts-only drops the notes and tips, leaving just the specifications; it is
# there for anyone who wants the mapping without the commentary.

# Guide index -> roster ordinal, for the amps whose guide title and catalog name
# genuinely disagree. Each was confirmed against the entry's own "Model:" line.
MANUAL_PAIRS = {
    152: "118",  # guide "Fox ODS Deep",        catalog "Fox ODS Mid"
    195: "61",   # guide "Matchbox Chieftain 1", catalog "Matchbox Chiefman 1"
    196: "62",   # guide "Matchbox Chieftain 2", catalog "Matchbox Chiefman 2"
    199: "197",  # guide "Mr Z Hwy 66",          catalog "Mr Z Highway 66"
    305: "78",   # guide "...Lead Mid Gain Bright", catalog "USA MK IV Lead Mid Bright"
    326: "219",  # guide "Vibrato Verb SRV",     catalog "Vibrato Verb Custom"
}

# Hand-written fields merged over whatever the guide yields, keyed by roster
# ordinal. Corrections belong here: edits made directly to the generated JSON
# are lost on the next run.
OVERRIDES: dict[str, dict] = {
    # "83": {"model": "EVH 5150III 100W, Red (high gain) channel"},
}

# "Label:" bullets promoted to their own field. Everything else becomes a note
# or a tip.
FIELDS = {
    "model": "model",
    "orig. cab": "orig_cab",
    "orig cab": "orig_cab",
    "dynacab": "dynacab",
    "controls": "controls",
    "preamp tubes": "preamp_tubes",
    "power tubes": "power_tubes",
    "tonestack location": "tonestack",
}
LABEL_RE = re.compile(r"([A-Za-z][A-Za-z0-9 .'’/-]{0,28}?)\s*:\s*(.*)", re.S)


def clean(fragment: str) -> str:
    """Flatten an XML fragment to plain text.

    An anchored figure interrupts the text it sits in, and the exporter pads the
    <Sect> block with its own line breaks. Every such split in this document
    lands mid-word ("CHAMP" + "LIFIER", "Recommende" + "d"), so the block and
    those line breaks are removed together -- but only the line breaks, since a
    space before the anchor is real content ("PRINCETONE " + "5F2").
    """
    s = re.sub(r"[\r\n]*<Sect>.*?</Sect>[\r\n]*", "", fragment, flags=re.S)
    s = re.sub(r"<[^>]+>", "", s)             # remaining Figure/ImageData/inline tags
    s = html.unescape(s)
    s = re.sub(r"[\x00-\x1f\x7f]", " ", s)    # PDF control glyphs
    return re.sub(r"\s+", " ", s).strip()


def squash(name: str) -> str:
    """Comparison key. '+' and '-' are kept: CH2+ and CH2- are different amps."""
    return re.sub(r"[^A-Z0-9+-]", "", name.upper())


def parse_toc(raw: str) -> dict[int, str]:
    """Entry number -> title, from the guide's own table of contents."""
    toc, pages = {}, []
    for link in re.findall(r"<Link>(.*?)</Link>", raw, re.S):
        m = re.match(r"^(\d{3})\s+(.*?)\s+(\d{1,3})$", clean(link))
        if m:
            toc[int(m.group(1))] = m.group(2).strip()
            pages.append(int(m.group(3)))

    if sorted(toc) != list(range(1, EXPECTED_ENTRIES + 1)):
        raise SystemExit(f"TOC is not a complete 1..{EXPECTED_ENTRIES} run "
                         f"(parsed {len(toc)} entries)")
    if any(a > b for a, b in zip(pages, pages[1:])):
        raise SystemExit("TOC page numbers are not monotonic; the title regex "
                         "is probably eating part of a name")
    return toc


# Headings and inline detail blocks. The negative lookahead rejects the many
# self-closing <Amp_Title/> spacers -- without it their non-greedy body runs on
# to the next real close tag and swallows the heading after it.
BLOCK_RE = re.compile(r"<(Amp_Title|Amp_Details)\b(?![^>]*/>)[^>]*>(.*?)</\1>", re.S)


def parse_bodies(raw: str, toc: dict[int, str]) -> dict[int, list[str]]:
    """Entry number -> its bullets, read in document order."""
    body = raw[raw.rfind("</TOC>"):]          # the TOC repeats every title

    blocks = []
    for m in BLOCK_RE.finditer(body):
        text = clean(m.group(2))
        if text:
            blocks.append([m.start(), m.group(1), text, False])   # last = is_anchor

    # Walk the expected 1..N run, claiming the next block that announces each
    # index. Anything left over is loose detail text belonging to the entry above.
    anchors, cursor = {}, 0
    for i in sorted(toc):
        marker = f"{i:03d}"
        while cursor < len(blocks) and marker not in blocks[cursor][2]:
            cursor += 1
        if cursor >= len(blocks):
            raise SystemExit(f"no body block found for guide entry {marker} "
                             f"({toc[i]!r})")
        blocks[cursor][3] = True
        anchors[blocks[cursor][0]] = i
        cursor += 1

    starts = sorted(anchors)
    collected: dict[int, list[tuple[float, str]]] = {i: [] for i in toc}

    def add(pos: float, text: str):
        """File a bullet under the entry whose heading most recently preceded it."""
        k = bisect.bisect_right(starts, pos) - 1
        if k >= 0:
            collected[anchors[starts[k]]].append((pos, text))

    for pos, kind, text, is_anchor in blocks:
        if kind != "Amp_Details":
            continue
        if is_anchor:
            # Heading and bullets share one block, separated by the "g" glyph.
            after = text.split(f"{anchors[pos]:03d}", 1)[-1]
            parts = [p.strip() for p in re.split(r"\s+g\s+", after)][1:]
            for n, part in enumerate(p for p in parts if p):
                add(pos + (n + 1) / (len(parts) + 2), part)   # keep them in order
        else:
            add(pos, text)                    # e.g. entry 022's lone Notes: line

    for m in re.finditer(r"<LBody>(.*?)</LBody>", body, re.S):
        text = clean(m.group(1))
        if text:
            add(m.start(), text)

    # Bullets were gathered per element type; sort back into document order so
    # that "Notes:" / "Tips:" still precede the bullets that continue them.
    return {i: [t for _, t in sorted(v)] for i, v in collected.items()}


def extract(bullets: list[str], with_prose: bool = False) -> dict:
    """Split an entry's bullets into structured fields, notes, and tips.

    The guide labels a bullet once ("Notes:", "Tips:") and lets the following
    unlabelled bullets continue that section, so section state carries over.
    """
    out: dict = {}
    notes: list[str] = []
    tips: list[str] = []
    section = notes

    for bullet in bullets:
        m = LABEL_RE.fullmatch(bullet)
        label = m.group(1).strip().lower() if m else None
        if label in FIELDS:
            out.setdefault(FIELDS[label], m.group(2).strip())
            continue
        if label in ("notes", "note"):
            section = notes
            bullet = m.group(2).strip()
        elif label in ("tips", "tip"):
            section = tips
            bullet = m.group(2).strip()
        if bullet:
            section.append(bullet)

    if with_prose:
        if notes:
            out["notes"] = notes
        if tips:
            out["tips"] = tips
    return out


def join_to_roster(toc: dict[int, str], roster: dict[str, str]) -> dict[int, str]:
    """Guide entry number -> roster ordinal.

    Pass 1 takes the longest roster name that prefixes the guide title (titles
    add decorative suffixes: "5F1 Tweed" -> "5F1 TWEED CHAMPLIFIER"). Pass 2
    handles the reverse. MANUAL_PAIRS covers real naming disagreements.
    """
    by_len = sorted(((squash(v), k) for k, v in roster.items()), key=lambda t: -len(t[0]))
    pairs: dict[int, str] = {}
    claimed: set[str] = set()
    leftover: list[int] = []

    for i in sorted(toc):
        if i in MANUAL_PAIRS:
            leftover.append(i)
            continue
        key = squash(toc[i])
        hit = next((o for n, o in by_len if n and key.startswith(n) and o not in claimed), None)
        if hit is None:
            leftover.append(i)
        else:
            claimed.add(hit)
            pairs[i] = hit

    still: list[int] = []
    for i in leftover:
        if i in MANUAL_PAIRS:
            still.append(i)
            continue
        key = squash(toc[i])
        cand = [o for n, o in by_len if o not in claimed and key and n.startswith(key)]
        if len(cand) == 1:
            claimed.add(cand[0])
            pairs[i] = cand[0]
        else:
            still.append(i)

    for i in still:
        ordinal = MANUAL_PAIRS.get(i)
        if ordinal is None:
            raise SystemExit(
                f"guide entry {i:03d} ({toc[i]!r}) matched no roster name; add it "
                f"to MANUAL_PAIRS after confirming its Model: line")
        if ordinal in claimed:
            raise SystemExit(f"MANUAL_PAIRS[{i}] = {ordinal} was already matched")
        claimed.add(ordinal)
        pairs[i] = ordinal
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("xml", nargs="?", type=Path, default=DEFAULT_XML,
                    help="guide XML export (default: %(default)s)")
    ap.add_argument("--facts-only", action="store_true",
                    help="omit the guide's notes and tips, keeping only the "
                         "modeled amp and its specifications")
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="override the output path")
    args = ap.parse_args()

    xml_path = args.xml
    out_path = args.out or OUT
    if not xml_path.exists():
        raise SystemExit(f"guide XML not found: {xml_path}")

    raw = xml_path.read_text(encoding="utf-8", errors="replace")
    roster = json.loads(CATALOG.read_text())["data"]["FM9_AMP_ROSTER"]

    toc = parse_toc(raw)
    bullets = parse_bodies(raw, toc)
    pairs = join_to_roster(toc, roster)
    print(f"guide entries : {len(toc)}")
    print(f"roster entries: {len(roster)}")

    missing = sorted(set(roster) - set(pairs.values()), key=int)
    if missing:
        print(f"WARNING: {len(missing)} roster ordinals have no guide entry:")
        for k in missing:
            print(f"  {k} = {roster[k]}")

    data, no_model, empty = {}, [], []
    for i, ordinal in sorted(pairs.items(), key=lambda kv: int(kv[1])):
        fields = extract(bullets[i], with_prose=not args.facts_only)
        fields.update(OVERRIDES.get(ordinal, {}))
        if not bullets[i]:
            empty.append(f"{ordinal} = {roster[ordinal]}")
        if "model" not in fields:
            no_model.append(f"{ordinal} = {roster[ordinal]}")
        data[ordinal] = {"fractal": roster[ordinal], "guide_index": i,
                         "guide_title": toc[i], **fields}

    stray = set(OVERRIDES) - set(data)
    if stray:
        raise SystemExit(f"OVERRIDES has ordinals not in the roster: {sorted(stray, key=int)}")

    out = {
        "schema_version": SCHEMA_VERSION,
        "device": "FM9",
        "content": "facts" if args.facts_only else "facts+prose",
        "keyed_by": "FM9_AMP_ROSTER ordinal (the DISTORT_TYPE wire value)",
        "source": "Amplifier Library Guide v1 (Comprehensive), XML export",
        "generated_by": "tools/build_amp_models.py",
        "warning": "Generated file. Hand edits are lost on regeneration; put "
                   "corrections in OVERRIDES in the generator instead. "
                   "'fractal' must stay equal to FM9_AMP_ROSTER[ordinal]; "
                   "fm9/registry.py enforces that at load time.",
        "amps": data,
    }
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    print(f"matched       : {len(data)}/{len(roster)}")
    print(f"with a model  : {len(data) - len(no_model)}")
    if args.facts_only:
        print("prose         : excluded (--facts-only)")
    else:
        print(f"with notes    : {sum(1 for v in data.values() if v.get('notes'))}")
        print(f"with tips     : {sum(1 for v in data.values() if v.get('tips'))}")
    if empty:
        print(f"no bullets at all ({len(empty)}): {', '.join(empty)}")
    if no_model:
        print(f"no Model: line ({len(no_model)}): {', '.join(no_model)}")
    rel = out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path
    print(f"wrote {rel} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
