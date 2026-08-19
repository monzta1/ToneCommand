# ToneCommand

**Speak, and your rig obeys.**

Natural-language tone control for the Fractal FM9: type "give me a Van Halen
Balance era tone with the flanger on the expression pedal", review the exact
parameter changes it proposes, confirm, and they land on the hardware over
USB MIDI with read-back verification.

## Demo

> Video coming soon.
<!-- DEMO PLACEHOLDER: prompt typed -> plan cards -> TRANSMIT -> FM9 screen
     changes -> riff with the pedal sweeping the jet flanger -->

## Credits & Prior Work

This project would not exist without the Fractal community's protocol work.
The heavy lifting of reverse-engineering the FM9-Edit editor protocol was
done by others; this project builds on it, verifies it against hardware,
and contributes corrections back (see Protocol Contributions below).

- **[mcp-midi-control](https://github.com/TheAndrewStaker/mcp-midi-control)**
  by **Stephen Staker** (TheAndrewStaker), Apache-2.0. The foundation. Its
  `SYSEX-MAP.md` is the best public documentation of the gen-3 Fractal
  editor protocol, byte-verified from hardware captures and binary mining.
  This project's `fm9/protocol.py` is a Python port of its TypeScript
  codec, and `config/fm9_catalog.json` is its FM9 parameter catalog,
  vendored verbatim. Roster data therein derives in part from
  **fractal-syx-codec** by Andrew Mercurio (Apache-2.0), and the grid-read
  cell layout was originally contributed by the **ai-tone-assistant**
  project (MIT).
- **[forgefx-midi](https://github.com/sKuhLight/forgefx-midi)** and
  **[ForgeFX](https://github.com/sKuhLight/ForgeFX)** by **sKuhLight**
  (Apache-2.0 and MIT respectively). Source of the FM9 modifier model:
  slot addressing, the binary-mined field map, and the bind sequence that
  makes expression-pedal assignments possible over MIDI. Re-implemented in
  Python here; ForgeFX was consulted, no code copied.
- **Fractal Audio Systems** publishes the official third-party MIDI spec
  ("Axe-Fx III MIDI for Third-Party Devices", Rev 1.4) that covers the
  documented command set: scenes, bypass, channels, names, tempo, and the
  effect ID table.

Full license reproductions and file-level provenance:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Safety

Designed so it cannot hurt a rig you care about:

- **Edit-buffer by default.** All changes go to the FM9's volatile working
  buffer, the same place front-panel knob turns go. Re-selecting the preset
  discards everything.
- **Confirm before send.** The natural-language layer only ever proposes a
  plan; nothing is transmitted until you approve it in the UI, and plans
  are pinned to the preset they were computed against (if you switch
  presets on the front panel, the stale plan is refused).
- **Whitelisted store.** Persisting to flash is only possible for a small
  range of designated test slots (default 133-140), enforced at the lowest
  code layer. Every other slot on the unit is untouchable.
- **Never touches firmware,** system settings, or global setup.
- **Back up first anyway.** Run a full Fractal-Bot backup before using any
  third-party MIDI tool, this one included.

## Protocol Contributions

Original findings from this project's hardware verification (FM9 firmware
11.00), offered back to the community projects above:

1. **FM9 grid insert requires a cell-select first.** The insert frame
   (fn 0x01 sub 0x32) alone lands the block on the device's internal
   cursor, not the frame's target cell. Sending the cell-select
   (sub 0x30, cell index as a raw uint32 in 5 septets) immediately before
   makes placement honor the target. Upstream documents the FM9 as not
   needing the select; that conclusion came from status-dump verification,
   which can confirm a block exists but not where it landed. Grid-read
   verification exposes the difference.
2. **Grid-read effect IDs alias mod 128.** The sub 0x2E grid bitstream
   stores the block id in 8 bits as (id << 1), so effect ids >= 128 wrap:
   FX Send (182) reads as 54, FX Return (186) reads as 58. Disambiguate
   against the fn 0x13 status dump.
3. **FM9 modifier source ordinal 11 = Pedal 2 (EXP/SW TIP),** confirmed
   physically. Upstream marks the FM9 source enum as uncaptured with an
   explicit warning against assuming the FM3's values; at least around the
   pedal entries, the FM3 ordering holds on the FM9.
4. **Documented dead ends** so nobody re-burns time on them: the sub 09 00
   GET always returns a zeroed value field on fw 11.00 (use the fn 0x1F
   bulk read instead); the sub 0x1F display-name query returns "NONE" for
   modifier source enums; live modulation (a moving pedal) is invisible to
   every known read, so pedal bindings must be verified physically.
5. **Shunt-replacement insertion.** Placing a block onto an existing shunt
   cell inherits the shunt's cables, which makes it possible to add effects
   into a preset's signal chain without touching the only partially decoded
   cable-drawing encoding at all.

## Disclaimer

Not affiliated with or endorsed by Fractal Audio Systems. Uses
reverse-engineered protocol; may break with firmware updates. Back up your
presets. Use at your own risk.

## Install / Setup

Tested on macOS (Apple Silicon) with Python 3.12 and an FM9 connected over
USB, on firmware 11.00 and 12.00.

```bash
git clone https://github.com/monzta1/ToneCommand.git
cd ToneCommand
python3 -m venv .venv
.venv/bin/pip install mido python-rtmidi fastapi "uvicorn[standard]" anthropic
```

Natural-language planning uses, in order of preference:
1. The Claude Code CLI, if installed and signed in (usage bills to your
   existing Claude subscription), or
2. The Claude API: put `ANTHROPIC_API_KEY=sk-ant-...` in a `.env` file at
   the repo root.

Run:

```bash
.venv/bin/python server.py
# open http://127.0.0.1:8909 with the FM9 connected and powered on
```

Sanity checks and utilities:

```bash
.venv/bin/python test_phase2.py   # 13-check hardware regression; run after any firmware update
.venv/bin/python build_133.py     # example: scripted full preset build (stores to test slot 133)
```

Notes:
- Do not run FM9-Edit and this tool at the same time; FM9-Edit resets the
  edit buffer when it connects. Stored presets are safe and remain fully
  viewable/editable in FM9-Edit afterwards.
- Firmware other than 11.x and 12.00 is untested; the editor protocol is
  unofficial and firmware-sensitive. `test_phase2.py` passing is the green
  light after any update.

## License

Apache License 2.0 for this project's code. Vendored and derived content
carries its own upstream copyrights; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
