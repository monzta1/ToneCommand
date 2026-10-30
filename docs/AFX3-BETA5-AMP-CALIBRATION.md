# Closed Beta 5 Amp calibration

This is an explicitly constructed developer component, not ordinary TC write
support. It does not change the app adapter, supported firmware registry,
shared FM9 guard, slot policies or UI/API capabilities. No production route or
launcher constructs `beta5_amp_calibration.Device`.

## Deliberately narrow scope

- Exact observed MK2 firmware response for `Oct 26 2026 12:42:45`, not generic
  FW33/raw97.00 or an alias to the earlier accepted profile.
- Current preset 327, scene 1, disconnected Amp/Cab/Drive/Pitch/NAM first
  instances on channel A. No Input, Output, cable, shunt or other block.
- Amp 1/A, 59 Bassguy Bright, independently read Level at most -12 dB.
- Four captured editor literal values only: Gain 4.6/5.0 and Mid 5.6/5.0.
  No zero, model, level, channel, scene, routing, modifier, NAM or Store SET.
- Native use is Windows, 64-bit Python 3.12 and mido. Injected scripted ports
  serve software tests; they are not hardware acceptance.

The final output boundary permits exact read forms or one thread-bound literal
under an active calibration review. Review and apply both require literal
`True` for muted external monitoring. A review binds the complete observed
baseline and expires after 60 seconds. It is connection-owned, replaced by a
new review and consumed before execution. A no-op sends no SET.

Before and after the SET, the component independently reads all current block
bulks, grid/status, all 32 complete modifier records, all eight scene names and
numeric displays. Only the addressed Amp A word and its display may change.
Unused modifier metadata is preserved. Reads settle/repeat; writes never retry.
An uncertain transport/readback outcome latches the connection. No automatic
restore, preset reload, Undo, Store or connection takeover is offered.

## Candidate hardware acceptance, 27 October 2026

The owner confirmed external mute and test-slot scope. Two separately reviewed
native SETs on 327 changed Gain 5.0 -> 4.6 and Mid 5.0 -> 5.6. Complete unrelated
observed state and independent numeric display/bulk verification passed. After
MIDI release, fresh Axe-Edit 1.15.02 independently displayed 4.60/5.60, model A,
Level -12 dB and the unchanged disconnected five-block grid.

Two separate **new reviews** restored 5.0/5.0, not an automatic rollback. A
second fresh Axe-Edit comparison and final native read-only comparison passed;
the complete observed baseline is restored. Exactly four parameter SETs were
sent, with no retries or Store. References 326/328 were not selected or changed.
Private reports/screenshots/captures are not published.

This candidate acceptance is separate from the earlier attempt through the
normal adapter, which correctly refused before output. That refusal remains
recorded, and the normal adapter continues to refuse these writes. No broad
Beta 5 or all-model/MK1/normal-GUI acceptance follows from this closed test.

Next work extends measured operation families with their own bounded execution
and independent verification, then tests the final registered TC SEND workflow.
MK1's full amp catalog is a separate experimental planner improvement, not
acceptance of this MK2 fingerprint on MK1. Dyna-Cabs remains a separate milestone.
