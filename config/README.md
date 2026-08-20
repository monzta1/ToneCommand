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
