# Axe-Fx III firmware migration

FW33 extends the FW32.06 implementation; it must not silently replace or discard
accepted functions. Reuse the shared musical behavior, validation and tests.
Retain firmware-specific encoders and independently verify device writes before
releasing a new profile. Unknown firmware stays read-only.

## Parameter coverage

The baseline has 75 first-instance parameter definitions. The exact tested
`33.00-beta.20261006` profile now retains all 75 and adds eight: five NAM controls,
two compressor automatic-mode controls and GEQ Q. The previously missing Wah
Control, eleven PEQ controls and Pitch Level passed captured-frame replay,
independent display/full-state checks and the ordinary TC numeric setters on
muted test preset 329 on 2026-10-18. Fresh Axe-Edit independently displayed the
resulting values. Definition coverage is not permission for every model, channel,
instance, route or scalar-zero value.

| Legacy group | FW33 migration |
|---|---|
| Amp (8), Cab (12), Delay (4), Reverb (3), Chorus (4), Output (1) | Definitions retained. Seven Amp knob encoders are firmware-specific; the measured route/channel/model boundaries still apply. |
| Drive (4), Compressor (6), GEQ (11) | Definitions retained; normal AMP/CAB building uses the measured T808 Mod, Modern VCA and 10 Band Variable Q profiles. Other legacy effect models are separate work. |
| Wah (10) | All definitions retained. Level now uses literal dB via opcode09; scalar Control uses opcode09 and knob/10. Modifier binding has separate acceptance below. |
| PEQ (11) | All five frequency/gain pairs and Level retained for PEQ1/A with the measured filter layout. Planner insertion and other instances/channels remain separate. |
| Pitch (1) | Pitch1 Level retained on the measured Dual Detune/A layout. The old Level setter never established musical pitch shifting. |

`firmware_parity.py` derives the inventory from the actual registries. Tests
require every missing definition and changed encoder to be explicitly accounted
for; removing another entry fails the migration contract. Nine encoders differ
from the parent. Extra instances are
checked separately: Amp 2 and additional Cab, Delay, Output, Reverb and Wah
numeric instances are not released by first-instance metadata. The older registry
also accepted synthetic instance addresses beyond physical availability; those
are not evidence of a successfully tested hardware block.

## Future firmware inheritance

`firmware_inheritance.compose` starts from the complete approved parent, makes
explicit encoding corrections and adds new controls. It rejects deletions,
missing replacements and conflicting wire addresses. The next firmware must
inherit the latest accepted child, including NAM additions and earlier fixes,
not rebuild a smaller parameter list or revert to an older wire encoder.

Regression tests retain the FW32.06 tests and require all 75 parent definitions
in the current child. An unknown firmware identifier remains read-only until
its identity and transport differences are checked; preserving behavior does
not mean sending old bytes blindly to a changed device.

For an offline migration report, run:

```powershell
.venv/Scripts/python.exe tools/afx3_firmware_parity.py --variant mk2
```

The report separates parameter coverage from model, instance, channel, routing,
controller and restore workflows. `--require-complete` fails while any tracked
workflow remains pending. It never opens MIDI or enables device writes.

## Wah controller acceptance

On 2026-10-18, the owner confirmed external audio muted. Axe-Edit captured native
allocation, External 1/2 source changes and Auto Engage Off/Fast Pos for Wah 1/2
on test preset 323. Complete native 25-word records matched the earlier FW32.06
comparison records. Eight direct existing-binding operations passed independent
full-state checks and fresh Axe-Edit inspection.

A normal reviewed 14-block fixture was built in empty preset 324 without Store.
Five further checks covered device-native Wah 1 modifier creation, both source
values and both modes. Fresh Axe-Edit confirmed External 2, full 0..10 range, linear
mapping and Auto Engage Off. The ordinary registered controller review/SEND
then changed that binding to External 1/Fast Pos and rejected token replay.

The controller workspace now reuses `pedal_control.py` on FW33/MK2. Each FW33
write has a single-use exact-frame boundary, full modifier and device-state
readback, and preservation checks. Only the target wah's bypass may respond to
source/Auto Engage changes. No global CC mapping or synthesized transfer curve
is written. Volume/Pan has its own independent acceptance below.

The normal FW33 AMP/CAB planner now combines Cry Babe voicing on shared channel
A, explicit scene bypass, External 1/2 and Off/Fast Pos. Its 201-action,
four-scene build from an empty preset passed normal review/SEND, complete
unrelated-state preservation, a final four-scene survey and fresh Axe-Edit
comparison on preset 329. Eight-scene synthetic and registered API tests cover
the same action grammar. The separate CONTROLLERS workflow remains available
for Wah 1/2. Neither workflow changes global CC mapping.

A further test used the actual selected AI through the registered TC plan and
SEND endpoints: all277 actions passed on empty329, with four complete scene
fingerprints. Fresh Axe-Edit independently showed the four selected amp models,
gains2/4/6/7, Cab IR/mixer and the requested Wah zero values/External2/Fast Pos.
The empty-grid preflight now checks future mixer/model layouts read-only before
the album execution session exists; the live SET guard is not bypassed.

Native allocation uses the first record with source NONE and absent target.
Unused records may retain an old parameter ordinal; requiring that ordinal to
be zero selected the wrong expected slot and blocked the build. The corrected
comparison preserves all other records, including their inactive metadata.
Only independent reads settle; uncertain writes are never retried.

Fast Pos can override scene bypass as the pedal moves. Choose Off for explicit
scene-controlled bypass. Physical pedal movement and audible bypass remain user
acceptance checks. A brighter wah filter does not implement pitch transposition.

## Volume controller and zero values

Volume/Pan 1 now reuses the approved controller implementation on exact
FW33/MK2. Three native allocation/source checks and two ordinary controller
review/SENDs passed on disconnected test preset 325. Fresh Axe-Edit confirmed
External 2, full 0..10 linear modifier mapping, Auto Engage Off, Type Volume and
0dB Level. All four channel layouts and all32 complete modifier records are
checked. No Volume Auto Engage, curve synthesis or global mapping is enabled.
The AMP/CAB planner's fixed route does not yet add a Volume block.

The approved scalar-zero variants are retained too: Wah Bias/Q Tracking/Fat,
Resonance/Drive, Amp Level, Output Level and Reverb Mix. Sixteen literal editor
frames, normal setters and independent display/full-state checks passed on
329/325. Each retains its captured opcode; there is no guessed opcode switch,
epsilon substitute or automatic fallback. Normal build staging still requires
quiet Amp/Output levels; a supported0dB setter is not permission to lift them.

## Remaining functional migration

- Integrate PEQ/Pitch Level and Volume insertion into normal musical design;
  retain the accepted Wah/controller behavior during refinement and resume.
- Measure extra physical instances and remaining effect model/channel domains.
  This includes remaining legacy Wah, Drive, Compressor, Delay and Reverb model
  variants. Preserve unrelated records on every test; an unchanged parameter
  address alone is not acceptance.
- Bring the more flexible FW32.06 construction/insertion behavior into the
  normal FW33 planner. Developer graph captures do not release arbitrary graph
  building, Send/Return loops or destructive reconstruction.
- Keep the eight-scene AMP/CAB and narrow NAM paths separate until their expanded
  routing/controller behavior is accepted. Keep recovery, Store and NAM-memory
  installation separately consented; no automatic write retry or rollback.
- Restore the older flexible AMP/CAB Reverb and multiple Delay voices in the
  normal FW33 planner; the current fixed template shares Delay/Chorus A.
- Exact raw-word restore remains unavailable on FW33. Parameter inheritance does
  not silently enable raw Undo or restoration of unsafe saved levels.

No preset was stored during this migration acceptance. Presets 326 and 328
were not changed. Static level/feedback limits and readback are not an audio
limiter or a claim of an audible recording match.
