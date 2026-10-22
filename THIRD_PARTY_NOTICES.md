# Third-Party Notices

This project stands on excellent prior work by the Fractal Audio community.
This file states exactly what came from where and under which license.

---

## mcp-midi-control (TheAndrewStaker)

- Repository: https://github.com/TheAndrewStaker/mcp-midi-control
- License: Apache License 2.0
- Copyright 2026 Stephen Staker

The primary foundation of this project's protocol layer.

- `config/fm9_catalog.json` is **copied verbatim** from that project's
  `packages/fractal-midi/catalog/fm9.json` (the FM9 parameter catalog:
  2,052 parameters with display ranges, plus the amp/drive/reverb rosters).
- `fm9/protocol.py` is **ported to Python** from that project's TypeScript
  (`packages/fractal-midi/src/`) and its protocol documentation
  (`SYSEX-MAP.md`): the fn 0x01 editor-protocol frames (parameter set,
  grid insert/clear/routing, preset and scene rename, store), the fn 0x1F
  whole-block read with its 0x74/0x75/0x76 burst format, the checksum, the
  display-to-wire scaling, the 8-to-7 packing algorithms, and the sub 0x2E
  grid-layout bitstream decode. Portions modified; see README "Protocol
  Contributions" for changes and corrections made in this project.
- `devices/axefx3/amp_cache.py` adapts the strict Gen-3 metadata record grammar
  from `parse-effectdefinitions-cache.ts` at commit
  `59047175cfc4f23e092931b54a7c54f2bffde3ea`, via this fork's prior local
  inventory tool. Modified for bounded read-only parsing and amplifier-only
  output; no private IR table, editor cache or new write authority is included.

Reproduction of that project's NOTICE (as required by Apache-2.0):

```
MCP MIDI Control
Copyright 2026 Stephen Staker

This product is licensed under the Apache License, Version 2.0.
See the LICENSE file for the full license text.

This repository also contains the `fractal-midi` package — a
codec-only TypeScript library that builds and parses Fractal Audio
SysEx wire bytes without depending on a MIDI transport. The same
trademark statement below applies to `fractal-midi`.

---

TRADEMARKS

This project is an unaffiliated community tool. "Fractal Audio",
"AM4", "Axe-Fx", "Axe-Fx II", "Axe-Fx III", "FM3", "FM9", and
related product names are trademarks of Fractal Audio Systems, Inc.
"ASM", "Ashun Sound Machines", and "Hydrasynth" are trademarks of
Ashun Sound Machines.

This project neither claims endorsement from, nor affiliation with,
Fractal Audio Systems or Ashun Sound Machines. It is a software
utility that communicates with hardware the user already owns via
publicly-documented SysEx, NRPN, and CC messages — including, for
Fractal devices, the protocol information Fractal Audio itself
publishes in its "MIDI for Third-Party Devices" specifications.

The package name `fractal-midi` uses the "Fractal" trademark
descriptively (nominative fair use) to identify the hardware the
library targets. The package does not claim official status and
is not affiliated with Fractal Audio Systems, Inc.

---

THIRD-PARTY SOFTWARE

This product includes software from the following projects, each
distributed under its own license. See the respective project's
LICENSE / NOTICE files in node_modules/ for full license text
when distributing in Object form.

  - @modelcontextprotocol/sdk (MIT License)
    https://github.com/modelcontextprotocol/typescript-sdk

  - node-midi (MIT License)
    https://github.com/justinlatimer/node-midi

  - zod (MIT License)
    https://github.com/colinhacks/zod

This product also includes gen-3 (Axe-Fx III / FM3 / FM9) protocol
data derived from:

  - fractal-syx-codec  (Apache License, Version 2.0)
    Copyright 2026 Andrew Mercurio ("BoodieTraps")
    https://github.com/drewmerc302/fractal-syx-codec
    The gen-3 preset-file format spec (FORMAT.md) and the read-ordinal
    effect-type roster tables. The Huffman/CRC codec here is a clean-
    room reimplementation from that spec; the roster name tables are
    derived from its data, independently cross-validated against our
    own hardware captures.

Additional development-only dependencies (TypeScript, tsx, jest,
etc.) are not redistributed in Object form and are listed in
package.json.
```

Pass-through credits carried by the content above and used here:

- **fractal-syx-codec** (Apache-2.0, Copyright 2026 Andrew Mercurio,
  "BoodieTraps"): origin of the effect-type roster tables included in
  the vendored catalog.
- **ai-tone-assistant** (MIT): origin of the grid cell bit-layout used by
  the sub 0x2E grid-read decode, as credited and cross-validated in
  mcp-midi-control's `gridLayout.ts`.

---

## forgefx-midi (sKuhLight)

- Repository: https://github.com/sKuhLight/forgefx-midi
- License: Apache License 2.0 (a fork of Stephen Staker's `fractal-midi`
  package, carrying his copyright, with sKuhLight's additions)

Source of the **FM9 modifier model** used by `fm9/protocol.py` and
`fm9/device.py`: modifier slot addressing (slot N = effect id 3 + N - 1,
32 slots), the field map (pid 0 source, pid 1/2 min/max, pid 8 target
effect id, pid 9 target param id, curve fields), and the FM3 modulation
source enum used as the starting hypothesis for the FM9's. Re-implemented
in Python; no code copied verbatim.

---

## ForgeFX (sKuhLight)

- Repository: https://github.com/sKuhLight/ForgeFX
- License: MIT
- Copyright (c) 2026 sKuhLight

Consulted for the `bindModifier` call sequence (bind target effect, target
param, then source) and the modifier address-model architecture. No code
copied.

---

## Fractal Audio Systems

The officially documented command set (scene select, block bypass and
channel, preset/scene name queries, tempo, tuner, looper, status dump, and
the effect ID table) comes from Fractal Audio's public specification
"Axe-Fx III MIDI for Third-Party Devices", Revision 1.4, applied to the
FM9 with its model byte 0x12.

"Fractal Audio", "Axe-Fx", "FM3", and "FM9" are trademarks of Fractal
Audio Systems, Inc. This project is not affiliated with or endorsed by
Fractal Audio Systems.

---

## HeadRush web editor bundle

- Source: the JavaScript the unit itself serves to a browser,
  `GET http://<unit>/static/js/main.<hash>.js` on the HeadRush's own HTTP
  server. Not a public download; it is what the device hands its own editor.
- Not redistributed by this project. The bundle is not in this repository;
  `tools/build_headrush_topologies.py` reads it from a unit or from a local
  copy, and commits only the derived table.

`config/headrush_topologies.json` records, per signal-path template, which of
the fourteen slots are common, which are on a parallel branch, and which belong
to an independent path. Those are facts about how the device routes audio, and
the device will not state them itself: it publishes the ten NAMES on
`Chain.Routing` and nothing about their shapes (#109).

Taken are the routing names, an ordering field, a vocals flag, and per slot a
screen position and a role integer. No code is copied and none is executed; the
bundle is parsed for those values and discarded. The file marks itself
`api_readable: false` and `provenance: "vendor editor bundle"` so that nothing
downstream can present it as something the unit answered.

"HeadRush" is a trademark of inMusic Brands, Inc. This project is not
affiliated with or endorsed by inMusic Brands.

## HeadRush published model list

- Source: HeadRush's own product page,
  <https://www.headrushfx.com/products/core/index.html>, which lists what each
  of its amp, cab and effect models emulates.
- Not redistributed by this project. The page is not in this repository;
  `tools/build_headrush_amp_models.py` reads a local copy, via the two
  generated artifacts described below.

`config/headrush_amp_models.json` is generated from that list. For each
HeadRush amp-model ordinal it records one fact: the real-world amplifier the
manufacturer says the model emulates.

This differs from the Amplifier Library Guide above in whose writing is
involved. That guide is a community document with an author, so its generator
takes specifications and leaves the prose. Here there is no prose to leave:
the page carries one attribution per model and nothing else.

What IS taken is the vendor's own wording of each attribution, verbatim,
including its trademark symbols, because paraphrasing a claim about whose amp
is being emulated would make it less checkable rather than more. The facts are
HeadRush's to state; the phrasing is theirs too, and it is reproduced only to
the extent needed to identify the gear.

"HeadRush" is a trademark of inMusic Brands, Inc. Amplifier and effect names
in the attributions, including Fender, Marshall, Vox, Orange, ENGL and Mesa
Boogie, are trademarks of their respective owners. They appear here, as on the
vendor's own page, to identify the equipment a model emulates. This project is
not affiliated with or endorsed by inMusic Brands or by any of those owners,
and the vendor states that its model list is for reference only.

The two inputs are both generated by script rather than transcribed, in
`HeadrushRigBuilder` (@bschmalz81401):

- `docs/device/model-catalog.json`, scraped from the product page above
- `src/lib/device-schema.generated.json`, fetched from a HeadRush unit over
  its own HTTP API, which is what supplies the ordinals

## Amplifier Library Guide

- Document: "Amplifier Library Guide v1 (Comprehensive)", a community
  reference for the Fractal amp library.
- Not redistributed by this project. The guide itself is not in this
  repository; `tools/build_amp_models.py` reads a local copy.

`config/amp_models.json` is generated from that guide. For each FM9 amp-roster
ordinal it records factual specifications only: the real-world amplifier
modeled, the original cab, DynaCab pairing, front-panel controls, tube
complement, and tonestack position.

The guide's prose notes and tips are the author's own writing, and some of them
quote other people. They are deliberately not reproduced here. The generator can
extract them with `--with-prose` for local use, to `config/amp_models.full.json`,
which is gitignored.

Amplifier specifications in that guide derive from manufacturer manuals and
websites.

---

## Yek's Guide to the Fractal Audio Drive Models

- Document: "Yek's Guide to the Fractal Audio Drive Models", a community
  reference by Alexander van Engelen (yek), publicly mirrored.
- Not redistributed by this project; `tools/build_drive_models.py` reads a
  local copy.

`config/drive_models.json` is generated from that guide's own section
headings ("<model> (based on <pedal>)"): factual model-to-pedal identity
only. The guide's prose synopses and tips are not reproduced. FM9 drive
models added after the guide's last update remain unmapped by design.

---

## Fractal Audio Wiki (community wiki), effect-type pages

- Pages: "Delay block", "Chorus block", "Multitap Delay block" (wiki.fractalaudio.com)
- Facts-only extraction of which real-world units the delay and chorus
  types reference, in config/effect_type_models.json via
  tools/build_effect_type_models.py. No wiki prose is reproduced.

---

## Fractal Audio Wiki (community wiki)

- Page: "Cab models", https://wiki.fractalaudio.com/wiki/index.php?title=Cab_models
- Not redistributed by this project. `tools/build_cab_models.py` reads a
  locally saved copy of the page.

`config/cab_models.json` records, for 2,235 of the FM9's 2,237 stock cab slots
and for all 45 firmware DynaCabs, the cabinet each was captured from, and where
the source gives them the manufacturer, size and microphone.

Facts only. Each `model` value is the cabinet's identity - make, model, speaker
complement - reduced to its first clause. The wiki's surrounding commentary and
its quotations from named individuals are deliberately not reproduced; the
generator's `--with-prose` mode keeps them in a gitignored local file instead.

Check the wiki's content licence before redistributing this file further.

## HeadRush web editor (normalisation tapers)

- Source: the web editor a HeadRush unit serves from its own HTTP port,
  `static/js/main.<hash>.js`. Not a public download and not vendored here.
- Not redistributed by this project. `tools/build_headrush_tapers.py` reads a
  local copy of that bundle and writes `config/headrush_tapers.json`.

The unit publishes an opaque integer per continuous parameter
(`x-options.normalizeAlgo`) and no formula for it, so the curve between the
0..1 wire value and the value the unit displays is not on the API. The editor
has to convert, so it carries the curves.

WHAT IS TAKEN IS FACTS, NOT CODE. Two things are recorded: the names of the
eleven curves, which is an enumeration the vendor ships in a file it serves,
and 990 reference vectors, which are numbers the vendor's own functions
produced when run. Neither is their expression of anything.

The vendor's SOURCE TEXT is deliberately not committed. A sha256 prefix of each
extracted fragment is kept instead, so that regenerating the table can be shown
to have read the same code without the code travelling with it. Anyone checking
the maths reads it from their own unit.

`config/headrush_topologies.json` takes slot geometry from the same bundle and
carries the same two fields, `provenance: "vendor editor bundle"` and
`api_readable: false`, so nothing downstream can present either as a device
read. That file arrives with #121 and may not be present yet depending on merge
order; this notice stands on its own either way.

"HeadRush" is a trademark of inMusic Brands, Inc. This project is not
affiliated with or endorsed by inMusic Brands.

## i18next

The local interface translation engine is i18next 26.5.5, distributed under
the MIT license. Source: https://github.com/i18next/i18next and npm package
https://www.npmjs.com/package/i18next/v/26.5.5. The unmodified browser build
is in `ui/languages/i18next.min.js`; its license is included beside it as
`i18next.LICENSE`. There is no runtime CDN or translation-service dependency.
