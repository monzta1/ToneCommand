# config/fm9_catalog.json - origin

`fm9_catalog.json` is copied verbatim from the mcp-midi-control project's
`packages/fractal-midi/catalog/fm9.json`:

- https://github.com/TheAndrewStaker/mcp-midi-control
- Copyright 2026 Stephen Staker
- Apache License 2.0

It is the FM9 device-true parameter catalog (2,052 parameters with display
ranges and typecodes, plus amp/drive/reverb rosters), mined from FM9-Edit
and hardware-validated by that project. The roster tables inside derive in
part from fractal-syx-codec (Apache-2.0, Copyright 2026 Andrew Mercurio).

See THIRD_PARTY_NOTICES.md at the repository root for the reproduced
NOTICE. If Fractal firmware updates renumber parameters, refresh this file
from the upstream catalog rather than hand-editing it.

# config/amp_models.json - origin

Generated, not vendored. Maps each `FM9_AMP_ROSTER` ordinal to the
real-world amp it models, so the planner can match "Plexi era" or "a
JCM800" to Fractal's oblique naming. Built by `tools/build_amp_models.py`
from the community Amplifier Library Guide: the modeled amp, original cab,
DynaCab pairing, controls, tubes, and tonestack position. Only the `model`
field reaches the planner prompt today; the rest is stored for future use.

The guide's prose notes and tips are its author's writing and are not carried
here. `--with-prose` extracts them for local use to
`config/amp_models.full.json`, which is gitignored so that build cannot
overwrite this one. See THIRD_PARTY_NOTICES.md for provenance.

Do not hand-edit: `fm9/registry.py` checks at load time that every record's
`fractal` field still equals `FM9_AMP_ROSTER[ordinal]` and raises
`AmpModelsStale` if a catalog refresh renumbered the roster. Corrections and
gap-fills belong in the generator's `OVERRIDES` table, then regenerate.

# config/cab_models.json - origin

Generated, not vendored. Maps the FM9's stock cabs to the real cabinets they
were captured from.

    cabs.0    FACTORY 1   1023/1024 mapped
    cabs.1    FACTORY 2   1023/1024 mapped
    cabs.3    LEGACY        189/189 mapped
    dynacabs                  45/45 mapped, keyed by name

IR-bank records are keyed by bank id then slot ordinal
(`FM9_CAB_ROSTERS_BY_BANK` / `FM9_CAB_BANK_NAMES`) and carry `model` plus the
cab name broken into `size`, `fractal_name`, `mic` and `variant`
("1x6 Dan-O 121" -> 1x6 / Dan-O / 121). Legacy records add `brand` and the
Fractal alias for that manufacturer ("GERMAN BOUTIQUE" = Bogner). DynaCabs are
a cab mode rather than IR slots, so they have no roster ordinal and are keyed
by name.

Facts only: `model` is the cabinet's identity reduced to its first clause. The
source's commentary and quotations are not reproduced. `--with-prose` keeps the
full text in `config/cab_models.full.json`, which is gitignored.

Built by `tools/build_cab_models.py` from a saved copy of the Fractal wiki's
"Cab models" page - the wiki sits behind a Cloudflare challenge that refuses
scripted fetches, so the page has to be saved from a browser first.

Two details worth knowing before changing the generator:

- For factory banks the description is **not in the table**. It is the
  "Based on ..." paragraph introducing each table, one table per cabinet.
  The table's Creator column is who made the IR, not what the cab is, and is
  dropped.
- The size/name/mic split is derived from the page's own grouping rather than
  from a microphone vocabulary: every row in a table is the same cabinet, so
  the tokens they all share are the name and the first that varies is the mic.

Corrections go in the generator's `CAB_OVERRIDES` / `DYNACAB_OVERRIDES`, not in
the generated JSON. The join is by slot (the wiki numbers each bank from 1, the
catalog from 0), with names compared only to confirm the offset still holds;
the build aborts if too few agree. `fm9/registry.py` raises `CabModelsStale` if
a record's `fractal` no longer matches the catalog roster.
