# Bounded Axe-Fx III Chorus support

Hardware checkpoint: 2026-10-06, Axe-Fx III FW 32.06, owner-approved
preset 323, external audio muted. No permanent Store.

## Reused upstream behavior

TC reuses FM9's read-only `plan_splice` geometry and shared grid/cable
builders. It does not copy the FM9 parameter catalogue by replacing a
product byte. Display-unit SET laws, bulk layouts and parameter addresses
remain independently calibrated for the Axe-Fx III.

Chorus 1 can be inserted immediately after Cab 1. An existing
route must be complete, contiguous, serial, on display row 3, with an
empty column immediately to its right. The later Drive/Compressor insertion
checkpoint also verifies moving and preserving downstream shunts, not using
them as disposable slack. Parallel routes, unsupported missing blocks,
other firmware and a full grid are refused. Multiple bounded additions are
performed sequentially; combined Drive/Compressor has native acceptance.

The captured rightward move preserves block data, unlike clear/reinsert.
TC moves rightmost blocks first, validates the entire grid after every
move, verifies all original bulk dumps, all modifier records and names,
then places Chorus and repairs only the disturbed cable span. A scoped
transport permit rejects this move outside the checked transaction.
Partial failure stops; it is not a topology rollback or automatic Undo.

## Verified controls

Chorus 1 Analog Stereo (model ordinal 3), four 32-word channels:

| Control | Parameter ID | Display units | SET 09 float |
| --- | --- | --- | --- |
| Rate | 2 | Hz | literal Hz |
| Depth | 4 | percent | value / 100 |
| Mix | 10 | percent | value / 100 |
| Level | 11 | dB | literal dB |

Depth, Mix and Level typed zero writes were captured and independently
verified. Level is restricted to at most 0 dB by TC's static safety policy.
Rate requires both bulk tempo word 3 and independent display Tempo NONE;
automatic Chorus tempo changes are not supported. Chorus 2 and other
chorus models remain unwritable despite the read-only model inventory.

Optional text designs expose chorus activation, rate, depth and mix per
scene, plus final level 0 dB. Omission preserves an existing Chorus.
A newly inserted Chorus is bypassed in configured scenes that omitted it.
This is a full preset design compiler, not an automatic promise that a
new full design preserves every existing amp/cab setting. Review all actions.

## Recorded acceptance

Passive Axe-Edit capture filenames, kept in ignored local backups:

- `20261006-101422-chorus-reuse-323.jsonl`: rightward Output/Reverb/Delay
  moves, Chorus display-unit setters.
- `20261006-102150-chorus-reuse-323-second.jsonl`: Analog Stereo selector
  and typed zero writes.
- `20261006-102726-chorus-insertion-restore-323.jsonl`: restoration of
  the developer test setup before TC's independent insertion acceptance.

These outgoing captures alone are not write verification. Independent
TC bulk/display reads provide the acceptance evidence below.

`chorus-tc-result-20261006.json`: normal TC single-use review and executor,
13/13 actions successful, zero skipped, no Store. After TC inserted Chorus,
the complete route was independently verified as Input 1 -> Wah 1 ->
Amp 1 -> Cab 1 -> Chorus 1 -> Delay 1 -> Reverb 1 -> Output 1.
The existing seven blocks, 32 modifier records, preset and scene names
remained unchanged. Final Chorus: Analog Stereo, channel A, engaged,
0.300 Hz, Depth 25%, Mix 20%, Level 0 dB, Tempo NONE.

Protected original values include Brit 800 Mod Gain 9 / Level -17 dB,
Output -6 dB, User 1 slot 28, Wah External 1 / Fast Pos,
Delay 280 ms / Feedback 22% / Mix 24% / Level 0 dB.
No claim of measured loudness, heard audio match or FM9 hardware acceptance.
The original main FM9 planner is unchanged; this feature is in `/axefx3`.

Software verification: all 520 `test_axefx3_*.py` cases passed locally in
simulator mode. Device-handle, capability-gate, UI-warning, FM9 splice and
IR-2 regression cases also passed in the combined compatibility run.
The real headless Chrome workspace test passed, including the Chorus
column, mobile layout, retained request, Enter newline and send consent.
