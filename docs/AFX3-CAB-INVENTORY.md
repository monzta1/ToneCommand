# FW33 cabinet inventory and four-IR mixer

Scope: exact `33.00-beta.20261006`, declared MK2, Cab1 A-D, within the
reviewed eight-scene AMP/CAB route. No IR/NAM memory installation, global
change, automatic Store or generic raw-Cab-write permission is added.

## Inventory and memory policy

The bundled Factory catalog contains 1024 names in each of Factory1 and
Factory2. Names and ordinals came from the exact editor definition tables;
no private User names or editor binary/cache is distributed. User imports
retain one-based display positions without silently splitting a bank at512:

| Display bank | FW33 wire bank | Positions | Eligible IR slots |
|---|---|---|---|
| Factory1 | 0 | 1-1024 | 1-4 |
| Factory2 | 1 | 1-1024 | 1-4 |
| User1 | 2 | 1-1024 | 1-4 |
| User2 | 3 | 1-1024 | 1-4, MK2 only in this profile |
| User3 FullRes | 6 | 1-64 | 3-4 |

Empty imported entries are not planner choices. FullRes remains a distinct
bank with explicit slot restrictions. The official FW33 beta release notes
state that MK1 replaces the entire User2 bank with NAM storage, while MK2
has separate NAM storage. Unknown NAM-era chassis fails closed. FW32.06
retains its independently tested older behavior; these changes do not
retroactively assert that its User addressing is the FW33 encoding.

The memory distinction is documented on page1 of the release notes in the
[official FW33 beta archive](https://www.fractalaudio.com/downloads/firmware-presets/axe-fx-3/33p0/axefxiii_dsp_rel_33p00_beta2.zip).

The separate additional Legacy bank4 is not Factory1/2. Its installed cache
and hardware boundary differed during calibration, so it remains blocked.

## Planner and execution

Each new Cab voice contains four explicit IR records: bank, slot, normal/
mute/solo mode, level and pan. The planner receives the complete available
Factory roster and nonempty imported User names. Existing Greenback/Recto
IR1-only aliases remain readable for older plans.

All slots are explicitly muted before selection, level and pan writes; final
modes are written last. The amp remains bypassed during initial voicing and
Output1 remains -18dB. The sum of linear gains of all non-muted IRs must be
at most one, even if solo temporarily excludes some normal IRs. This is a
conservative coherent-sum budget, not an acoustic limiter or a guarantee of
equal IR sensitivity, safe physical loudness or matching tone.

Every operation remains bound to the generated review grammar and exact
active parameter/value. Fresh whole-state and independent display readback
detect changes outside the addressed word. Unknown results stop without a
write retry, alternate opcode, rollback or preset reload. A Cab selection
does not automatically unmute another IR. IR1/2 do not mean stereo L/R.

The collapsible CAB LIBRARY searches all metadata, showing up to100 matches
at once. The current mixer panel distinguishes IN MIX, MUTED, SOLO and
EXCLUDED BY SOLO with actual level/pan. Only the current channel is read;
an inactive channel is not inferred from it. Review shows the planned mix.

## Recorded acceptance, 2026-10-16

- Independent Axe-Edit captures cover Factory1/2 and User1/2 boundary
  positions1/512/513/1024 on all four slots, plus level/pan/zero values.
  Separate measurements cover all four mode fields, FullRes3/4 boundaries,
  and selectors/mixer controls on Cab channels B/C/D.
- A fixed270-frame native replay, bound to test322, verifies every addressed
  selector/channel/mixer word and preserves the rest of the whole device
  snapshot. Numeric/mode values also receive independent display readback.
- The actual configured AI produces an explicit four-voice mixer design
  from the full metadata reference. Normal registered review/SEND completes
  339/339 actions on322. Eight native scene surveys verify every bank, slot,
  mode, level and pan. Factory1/2, User1/2, two/four-IR blends and IR4-only
  membership are represented. No preset or IR/NAM memory is stored.
- After TC releases MIDI, Axe-Edit independently verifies all eight scene
  names, Cab channels, four IR names/banks/positions, visible level/pan and
  mute/solo indicators, with screenshots. It closes normally without Save.
- A fresh native check verifies the tightened exact-value Cab wire gate and
  full-state preservation. The test amp is left bypassed under external mute.
- Mandatory gates, all FX3 suites and explicit text-encoding checks pass1917
  tests. Focused exact-wire/mix/preservation regressions also pass. Real Chrome
  mocked workflow tests cover the full catalog search, XSS-safe User labels,
  muted-IR display, retained requests, review/send consent and existing routes.

This does not claim all2048 addresses were individually selected on every
channel, that occupied FullRes audio was auditioned, or that a measured mix
sounds like a reference. The local FullRes bank was empty; no IR was installed.
Presets326/328 and shared IR/NAM memory were not written during these tests.
