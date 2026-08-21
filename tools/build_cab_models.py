#!/usr/bin/env python3
"""Generate config/cab_models.json from the Fractal wiki's "Cab models" page.

The FM9 cab rosters in config/fm9_catalog.json give Fractal's own cab names
("1x6 Dan-O 121", "4x12 GERMAN BOUTIQUE"). They do not say what real cabinet
each one was captured from. The wiki does, so this script joins the two and
writes a sidecar, leaving the vendored catalog untouched.

Covers all three stock IR banks plus the firmware DynaCabs:

    bank 0  FACTORY 1   1024 slots
    bank 1  FACTORY 2   1024 slots
    bank 3  LEGACY       189 slots
    dynacabs              45 entries, keyed by name (they have no roster slot)

Facts only. Each record's `model` is the cabinet's identity -- make, model,
speaker complement -- reduced to its first clause; the wiki's surrounding prose,
commentary and quotations are not reproduced. `--with-prose` writes the full
source text to config/cab_models.full.json, which is gitignored.

For the factory banks the description is not in the table at all -- it is the
"Based on ..." paragraph that introduces each table, one table per physical
cabinet. The table's Creator column names whoever made the impulse response,
not the cab, and is dropped. Legacy rows carry their description in a Comments
column instead, and are grouped by manufacturer headings.

Factory cab names decompose as `<size> <fractal name> <mic> [variant]`. Rather
than guess at a microphone vocabulary, the split is derived from the page's own
grouping: every row in one table is the same cabinet, so the tokens they all
share are the name and the first token that varies is the mic.

Input is a saved copy of the page, because the wiki sits behind a Cloudflare
challenge that refuses scripted fetches (plain curl gets 403). Open

    https://wiki.fractalaudio.com/wiki/index.php?title=Cab_models

in a browser and save it, by default to:

    ~/Downloads/FractalWiki/Cab_models.html

Usage:
    .venv/bin/python tools/build_cab_models.py                # facts, committed
    .venv/bin/python tools/build_cab_models.py --with-prose   # + raw text, local

The join is by slot, not by name: the wiki numbers each bank from 1 and the
catalog from 0. Names are compared only to confirm that offset still holds.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "config" / "fm9_catalog.json"
OUT = ROOT / "config" / "cab_models.json"
OUT_PROSE = ROOT / "config" / "cab_models.full.json"
DEFAULT_HTML = Path.home() / "Downloads/FractalWiki/Cab_models.html"

SCHEMA_VERSION = 2
SLOT_OFFSET = -1                  # wiki slot 1 == catalog ordinal 0
FACTORY_SECTION = "Axe-Fx III, FM3, FM9"
DYNACAB_SECTION = "DynaCabs"

# wiki H2 -> (catalog bank id, expected slots, minimum names that must agree
# before the mapping is trusted)
BANKS = {
    "Factory Bank 1": ("0", 1024, 1000),
    "Factory Bank 2": ("1", 1024, 1000),
}
LEGACY_BANK, LEGACY_COUNT, LEGACY_MIN_AGREE = "3", 189, 170

# Corrections and gap-fills, merged over whatever the page yields. Edits made
# directly to the generated JSON are lost on the next run; put them here.
#
# Two slots have no row on the wiki at all and stay unmapped rather than guessed:
#   bank 0 slot 210 = "1x12 Class-A 5W 57 Center TS"
#   bank 1 slot 839 = "4x12 Recto ST 57M A YA"
CAB_OVERRIDES: dict[str, dict] = {
    # "0/210": {"model": "..."},
}
DYNACAB_OVERRIDES: dict[str, dict] = {
    # "1x12 AC20": {"model": "..."},
}

SIZE_RE = re.compile(r"^(\d+x\d+[a-z]?)\s+(.*)$")   # 1x12, 4x12, 1x12c, 1x12o

# Section headings that group by speaker or category rather than manufacturer.
NOT_A_BRAND = {
    '15" SPEAKERS', "ALNICO BLUE and SILVER", "BASS CABINETS", "FAR-FIELD IRs",
    "EV 12L/12S", "G12-65", "G12T-75", "G12H", "G12L", "G12M (GREENBACK)",
    "V30", "EMINENCE", "EVH 5150 / PVH 6160",
}


class WikiPage(HTMLParser):
    """Collect paragraphs and wikitable rows, tagged with the headings above them.

    MediaWiki's current skin wraps headings as <div class="mw-heading mw-headingN">
    rather than emitting a bare <hN>, and tables sit nested inside layout divs,
    so heading state has to be tracked across the whole document rather than by
    walking siblings.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.h1 = self.h2 = None
        self._heading = None
        self._buf: list[str] = []
        self._in_p = self._in_table = self._in_cell = False
        self._row: list[str] = []
        self._table: list[list[str]] = []
        self.events: list[tuple] = []      # ("p"|"table", h1, h2, payload)

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        if tag == "div" and "mw-heading" in cls:
            m = re.search(r"mw-heading(\d)", cls)
            if m:
                self._heading, self._buf = int(m.group(1)), []
        elif tag == "p" and not self._in_table:
            self._in_p, self._buf = True, []
        elif tag == "table":
            self._in_table, self._table = True, []
        elif tag == "tr" and self._in_table:
            self._row = []
        elif tag in ("td", "th") and self._in_table:
            self._in_cell, self._buf = True, []

    def _text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._buf)).replace("[edit]", "").strip()

    def handle_endtag(self, tag):
        if tag == "div" and self._heading:
            t = self._text()
            if self._heading == 1:
                self.h1, self.h2 = t, None
            elif self._heading == 2:
                self.h2 = t
            self._heading, self._buf = None, []
        elif tag == "p" and self._in_p:
            t = self._text()
            if t:
                self.events.append(("p", self.h1, self.h2, t))
            self._in_p, self._buf = False, []
        elif tag in ("td", "th") and self._in_cell:
            self._row.append(self._text())
            self._in_cell, self._buf = False, []
        elif tag == "tr" and self._in_table and self._row:
            self._table.append(self._row)
            self._row = []
        elif tag == "table" and self._in_table:
            self.events.append(("table", self.h1, self.h2, self._table))
            self._in_table, self._table = False, []

    def handle_data(self, data):
        if self._in_cell or self._heading or self._in_p:
            self._buf.append(data)


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def identity(text: str | None) -> str | None:
    """Reduce a source description to the cabinet's identity.

    Drops the "Based on" framing, the "Source:" note, footnote markers and any
    sentences past the first -- what follows is commentary and quotations, which
    are not reproduced. "Based on a vintage Danelectro with a single 6\" speaker.
    Source: Cab Pack 6." becomes "vintage Danelectro with a single 6\" speaker".
    """
    if not text:
        return None
    s = re.sub(r"\s*Source:.*$", "", text, flags=re.I | re.S)
    s = re.sub(r"\[\d+\]", "", s)                                  # footnote refs
    s = re.sub(r"^based on\s+", "", s.strip(), flags=re.I)
    s = re.split(r'(?<=[a-z0-9"\u201d)])\.\s+(?=[A-Z\u201c"])', s)[0]   # first sentence
    s = re.sub(r"^(a|an|the)\s+", "", s.strip(), flags=re.I)
    s = re.sub(r"\s+", " ", s).strip().rstrip(".").strip()
    return s or None


def based_on(paragraphs: list[str]) -> str | None:
    """The 'Based on ...' line introducing a table, with its Source: note removed.

    Most tables are preceded by exactly that one paragraph, but a few also carry
    intro prose or a following Tip, so pick by prefix rather than by position.
    """
    for text in reversed(paragraphs):
        if re.match(r"^based on\b", text, re.I):
            return re.sub(r"\s*Source:.*$", "", text, flags=re.I | re.S).strip()
    return None


def split_brand(heading: str) -> tuple[str | None, str | None]:
    """'BOGNER ("GERMAN BOUTIQUE")' -> ('BOGNER', 'GERMAN BOUTIQUE')."""
    if heading in NOT_A_BRAND:
        return (None, None)
    m = re.match(r'^(.*?)\s*\("(.+?)"\)$', heading)
    return (m.group(1).strip(), m.group(2).strip()) if m else (heading.strip(), None)


def creator_abbrevs(events) -> set[str]:
    """Creator initials, read from the page's own Abbrev./Creator legend."""
    out = {"FAS"}
    for kind, _, _, payload in events:
        if kind == "table" and payload and [c.lower() for c in payload[0]][:1] == ["abbrev."]:
            out.update(r[0].strip() for r in payload[1:] if r and r[0].strip())
    return out


def split_name(rows: list[tuple[int, str]], creators: set[str]) -> dict[int, dict]:
    """Split one table's cab names into size / fractal name / mic / variant.

    Every row here is the same cabinet, so the leading tokens they all share are
    the name and the first token that differs is the microphone.
    """
    parsed = []
    for slot, full in rows:
        m = SIZE_RE.match(full)
        size, rest = (m.group(1), m.group(2)) if m else (None, full)
        parsed.append((slot, size, [t for t in rest.split() if t not in creators]))

    seqs = [toks for _, _, toks in parsed]
    shared = 0
    while all(len(s) > shared + 1 for s in seqs) and len({s[shared] for s in seqs}) == 1:
        shared += 1

    out = {}
    for slot, size, toks in parsed:
        tail = toks[shared:]
        out[slot] = {
            "size": size,
            "fractal_name": " ".join(toks[:shared]) or None,
            "mic": tail[0] if tail else None,
            "variant": " ".join(tail[1:]) or None,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("html", nargs="?", type=Path, default=DEFAULT_HTML,
                    help="saved Cab models page (default: %(default)s)")
    ap.add_argument("--with-prose", action="store_true",
                    help="keep the source's full descriptions verbatim instead of "
                         "reducing them to the cabinet's identity. Writes to "
                         "config/cab_models.full.json, which is gitignored: that "
                         "text is the wiki's own prose and is not redistributed.")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()
    out_path = args.out or (OUT_PROSE if args.with_prose else OUT)
    keep = (lambda s: s) if args.with_prose else identity
    if not args.html.exists():
        raise SystemExit(f"saved page not found: {args.html}\nOpen the wiki page in a "
                         f"browser and save it there (scripted fetches are blocked).")

    page = WikiPage()
    page.feed(args.html.read_text(encoding="utf-8", errors="replace"))
    creators = creator_abbrevs(page.events)
    roster = json.loads(CATALOG.read_text())["data"]["FM9_CAB_ROSTERS_BY_BANK"]

    # Pair every cab table with the paragraphs that introduce it.
    tables, pending = [], []
    for kind, h1, h2, payload in page.events:
        if kind == "p":
            pending.append(payload)
            continue
        header = [c.lower() for c in payload[0]] if payload else []
        if header[:2] == ["slot", "cab name"]:
            tables.append((h1, h2, list(pending), payload))
        pending = []

    # DynaCabs are not IR slots and have no roster ordinal, so they are keyed by
    # name. The wiki's header calls column 1 "Slot", but it holds the cab name.
    dynacabs: dict[str, dict] = {}

    for h1, h2, paras, rows in tables:
        if h1 != DYNACAB_SECTION:
            continue
        for cells in rows[1:]:
            if len(cells) < 2 or not cells[0].strip():
                continue
            name = htmllib.unescape(cells[0]).strip()
            rec = {"fractal": name}
            model = keep(htmllib.unescape(cells[1]).strip())
            if model:
                rec["model"] = model
            rec.update(DYNACAB_OVERRIDES.get(name, {}))
            dynacabs[name] = rec

    scraped: dict[str, dict[int, dict]] = {b: {} for b in (*[v[0] for v in BANKS.values()],
                                                           LEGACY_BANK)}
    for h1, h2, paras, rows in tables:
        body = [(int(c[0]), htmllib.unescape(c[1]).strip(), c[2] if len(c) > 2 else "")
                for c in rows[1:] if len(c) >= 2 and c[0].strip().isdigit()]
        if not body:
            continue
        if h1 == FACTORY_SECTION and h2 in BANKS:
            bank = BANKS[h2][0]
            desc = based_on(paras)
            parts = split_name([(s, n) for s, n, _ in body], creators)
            for slot, name, _ in body:
                scraped[bank][slot] = {"wiki_name": name, "based_on": desc, **parts[slot]}
        elif h1 == "Legacy":
            brand, alias = split_brand(h2 or "")
            for slot, name, comment in body:
                scraped[LEGACY_BANK][slot] = {
                    "wiki_name": name,
                    "based_on": htmllib.unescape(comment).strip() or None,
                    "brand": brand, "fractal_alias": alias, "group": h2,
                }

    out_banks: dict[str, dict] = {}
    report = []
    plan = [(b, n, mn) for b, n, mn in
            [(*BANKS[k], ) for k in BANKS] ] + [(LEGACY_BANK, LEGACY_COUNT, LEGACY_MIN_AGREE)]
    for bank, expected, min_agree in plan:
        src, cat = scraped[bank], roster[bank]
        if len(cat) != expected:
            raise SystemExit(f"bank {bank}: catalog has {len(cat)} slots, expected {expected}")
        records, agree, no_row, no_desc = {}, 0, [], 0
        for ordinal, cab in sorted(cat.items(), key=lambda kv: int(kv[0])):
            row = src.get(int(ordinal) - SLOT_OFFSET)
            if row is None:
                no_row.append(f"{ordinal} ({cab})")
                continue
            rec = {"fractal": cab, "slot": int(ordinal)}
            model = keep(row.get("based_on"))
            if model:
                rec["model"] = model
            else:
                no_desc += 1
            for f in ("size", "fractal_name", "mic", "variant", "brand",
                      "fractal_alias", "group"):
                if row.get(f):
                    rec[f] = row[f]
            if norm(row["wiki_name"]) == norm(cab):
                agree += 1
            else:
                rec["wiki_name"] = row["wiki_name"]
            rec.update(CAB_OVERRIDES.get(f"{bank}/{ordinal}", {}))
            records[ordinal] = rec
        if agree < min_agree:
            raise SystemExit(f"bank {bank}: only {agree} of {len(records)} names agree "
                             f"(need {min_agree}); the slot offset looks wrong -- "
                             f"refusing to write a bad mapping")
        out_banks[bank] = records
        report.append((bank, len(records), expected, agree, no_desc, no_row))

    out = {
        "schema_version": SCHEMA_VERSION,
        "device": "FM9",
        "keyed_by": "FM9_CAB_ROSTERS_BY_BANK bank id, then slot ordinal",
        "banks": {b: json.loads(CATALOG.read_text())["data"]["FM9_CAB_BANK_NAMES"][b]
                  for b in out_banks},
        "content": ("facts+prose" if args.with_prose else
                    "facts-only: cabinet identity, no prose reproduced"),
        "source": "Fractal Audio Wiki, 'Cab models'",
        "generated_by": "tools/build_cab_models.py",
        "warning": "Generated file. Hand edits are lost on regeneration. "
                   "'fractal' must stay equal to FM9_CAB_ROSTERS_BY_BANK[bank][slot]; "
                   "fm9/registry.py enforces that at load time.",
        "cabs": out_banks,
        "dynacabs": dynacabs,
    }
    out_path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")

    total = sum(len(v) for v in out_banks.values())
    print(f"{'bank':>5} {'mapped':>12} {'names agree':>12} {'no model':>12}")
    for bank, n, expected, agree, no_desc, no_row in report:
        print(f"{bank:>5} {f'{n}/{expected}':>12} {f'{agree}/{n}':>12} {no_desc:>12}")
        for m in no_row:
            print(f"        no wiki row for slot {m}")
    print(f"{'dyna':>5} {f'{len(dynacabs)}':>12} {'-':>12} "
          f"{sum(1 for v in dynacabs.values() if not v.get('model')):>12}")
    print(f"\ntotal IR slots mapped: {total}")
    print(f"dynacabs mapped      : {sum(1 for v in dynacabs.values() if v.get('model'))}/{len(dynacabs)}")
    print(f"with a model         : {sum(1 for v in out_banks.values() for r in v.values() if r.get('model'))}")
    print(f"with a mic           : {sum(1 for v in out_banks.values() for r in v.values() if r.get('mic'))}")
    rel = out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path
    print(f"wrote {rel} ({out_path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
