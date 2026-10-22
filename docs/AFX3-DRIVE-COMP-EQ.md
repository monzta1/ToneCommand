# Existing Drive, Compressor and EQ core controls

## Muted hardware checkpoint, 2026-10-06

Owner authorized TestPreset 323, confirmed external audio stays muted and
placed the test blocks manually. No permanent Store was authorized or sent.
The captured serial route was Input 1 -> Drive 1 -> Compressor 1 -> Amp 1 ->
Cab 1 -> GEQ 1 -> PEQ 1 -> Output 1. All four new test effects remained
bypassed after testing. Amp, Cab, Input and Output settings were preserved.

Passive Axe-Edit III outgoing evidence:
`20261006-105543-drive-comp-eq-main-323.jsonl`, with guarded numeric UI
events in `effects-ui-events-20261006.jsonl`. Independent native TC
`tone_review.Reviews.prepare/send` then verified **88/88** writes across
32 controls: test values, separately captured zeros where applicable, and
restoration to the independently read starting values. Checkpoints are
local/gitignored in `backups/integration-20260929/effects-tc-*.json`.

Full bulk checks verified unchanged Input/Amp/Cab/Output, other effect
channels, grid, modifier records, names and block/channel/bypass states.
An additional native review verified **8/8** engage/bypass round trips,
returning all four blocks to bypass with exact full-state equality.
Parameter acceptance is on channel A. Per-scene A-D compilation is tested
offline, with read-only mode/layout checks for every future selected channel.
It is not evidence that every model, filter type or instance is supported.

## Captured units and profiles

| Existing first block | Mode gate | Controls | SET 01 09 float |
|---|---|---|---|
| Drive, EID 118 | Rat Distortion, word 0 = 0 | Distortion, Filter, Level, Mix | knob / 10; Mix / 100 |
| Compressor, EID 46 | Modern VCA, word 12 = 0 | Threshold, Ratio, Attack, Release, Level, Mix | literal dB/ratio; time in seconds; Mix / 100 |
| GEQ, EID 50 | 10 Band Variable Q, word 15 = 4 | Ten band gains, Level | literal dB |
| PEQ, EID 54 | filter words 15-19 = 0 | Five frequencies, five gains, Level | literal Hz/dB |

Compressor threshold, GEQ band 1 and PEQ frequency 1 really use parameter
ID 0. Treating every pid 0 as a model selector breaks both reading and
writing these settings. The narrow first-block exception permits passive
01 10 display queries and canonical numeric SETs, not model-selector GETs
or an active zero SET masquerading as a query.

GEQ band order: 31/63/125/250/500/1000/2000/4000/8000/16000 Hz.
PEQ filter types remain Shelving/Peaking/Peaking/Peaking/Shelving. The Q
wheel generated increment/decrement gestures, not a captured absolute
numeric setter. Q is therefore deliberately not writable in this checkpoint.

## Application and safety boundaries

The AI design schema accepts optional `drive`, `compressor`, `geq` and
`peq` per scene. Deterministic compilation selects the corresponding
channel, bypasses while voicing, writes the final level and applies the
requested final bypass state. Omission preserves existing settings.
The browser review shows the extra voicing, optional model and units per scene.

Drive/Compressor can now be inserted before Amp in the bounded topology
described below; GEQ/PEQ must already exist after Cab.
Omitted Drive/Compressor model choices preserve existing models;
EQ filter types, Q and modifiers are always preserved. A complete
bulk layout and the mode on every addressed future channel are validated
before the first plan write, and rechecked in each display setter. A failure
stops the batch; partial edits can remain. No guessed fallback opcode,
automatic destructive rebuilding or global controller setup is enabled.

Drive Level is a 0-10 knob, **not dB and not calibrated unity gain**. Only
the pinned captured AFX3 Drive profiles have a 0..5 automation allowance. FM9 generic
unknown-unit level controls retain their refusal. EQ gains and effect dB
levels remain <= 0. Compressor attack/release in the design are milliseconds.
External mute is still mandatory; none of these limits measures loudness,
feedback stability or prevents damage independently of the physical setup.
No audio comparison, positive EQ boost, raw restoration or acoustic match
has been proven by this test. The later insertion checkpoint below is separate
from the original existing-block control evidence.

## Captured model-selection follow-up, 2026-10-06

The owner manually opened Axe-Edit after TC released its MIDI port. Passive
capture `20261006-125928-drive-comp-models-323.jsonl` recorded five model
selectors and numeric controls in the newly selected profiles:

| First block | Model selector | Captured selectable models |
|---|---|---|
| Drive 1, 118 | 01 09, pid 0 | Rat Distortion (0), T808 OD (6), T808 Mod (8) |
| Compressor 1, 46 | 01 09, pid 12 | Modern VCA Compressor (0), Classic VCA Compressor (13) |

Zero model writes were followed by independently observed return to the
named model, not accepted merely as ambiguous zero/get capture events.
Axe-Edit was closed normally before native TC took the MIDI port. Native
`tone_review.Reviews.prepare/send` verified **81/81 actions**: all five
model transitions, captured numeric values, supported zeros and restoration
of starting display values. Passive bulk independently confirmed return to
Rat/Modern models. Reports are private `models-tc-*.json`.

Full checks preserved Input/Amp/Cab/Output/GEQ/PEQ bulk, modifiers, grid,
names, channel/bypass states and Drive/Compressor channels B-D. Both test
blocks stayed bypassed; no Store or preset reload occurred. Hardware model
acceptance is channel A. A-D addressing and isolation are tested offline,
not claimed as four-channel hardware acceptance.

The design schema has an optional `model` in `drive` and `compressor`.
The compiler uses only the exact captured names. An omitted/null model
adds no reset. A model transition requires an explicit preceding channel
and final level before engage or a transition away. Different profiles or
firmware still fail closed before writes. Model selectors are bulk-read,
never queried using an active SET. Compressor threshold remains numeric
pid 0. Model 13 must never be sent to that threshold address.

Model changes leave the block bypassed and restage its level afterwards.
Drive uses captured Level knob 0, Compressor uses at most -12 dB. This is
not calibrated unity or a limiter. External mute and physical audition are
still necessary. No existing block or shunt was removed in the model-selection
follow-up; the later insertion test received separate removal permission.

Final software gates passed **714 tests**, 114.71 seconds, six workers,
including all AFX3 tests and mandatory device-handle/capability/UI-warning
plus invariant safety gates. Report: `models-final-gates-20261006.xml`.
Installed headless Chrome passed the existing workspace checks and new
model-name rendering. TC was restarted disconnected via SIGTERM, then
reconnected to323 with the512-name User1 names-only catalogue restored.
No paid AI generation, Store or acoustic comparison was performed.

## Automatic insertion acceptance, 2026-10-06

The owner explicitly authorized temporary removal/recreation of Drive1 and
Compressor1 on muted TestPreset323. No permanent Store was authorized.
Previously recorded Axe-Edit DELETE/left-drag frames were reused only for
developer fixture setup. The application and AI have no delete action.
Fixture permissions require FW32.06, target323, exact transaction frames,
test columns2/3 and live Drive1/Compressor1. Leftward fixture moves require
an additional scoped permit; normal insertion permits only rightward moves.

A readback stop exposed two DELETE/leftward-drag details: deleting a block
also clears the following cell's incoming cable, as does moving its source
left. Fresh independent grid/bulk reads confirmed all protected settings
held. Only that exact observed partial state was resumed; no blind retry or
automatic routing rollback was attempted. Fixture compaction then repaired
the known adjacent span and independently verified a complete serial route.

Native `insertion-shunt_probe-*.json` verifies a shunt/output round trip,
including exact restoration of all original bulk, grid, names and modifiers.
Each individual missing Drive/Compressor was then inserted by TC's normal
single-use review/executor path: **3/3 actions each**. Fresh defaults read as
Rat/Modern VCA with complete four-channel layouts. Both original shunts and
all protected state were preserved, and the new blocks were bypassed.

Both blocks were removed again for the combined test. One normal review
then verified **20/20 actions**, none skipped: automatic placement, explicit
channelA, T808 OD and Modern VCA selection, ten numeric control writes and
final bypass. Independent reads confirmed Drive6/Tone4/Mix100/Level2;
Compressor threshold-30dB/ratio4/attack5ms/release249.99ms/mix75/level-12dB.
Other channels of the newly placed blocks match the immediately post-build
snapshot. These are not claims that deletion retained their previous data.
Input/Amp/Cab/GEQ/PEQ/Output bulk, names and every modifier stayed unchanged.
Final grid equals the original ten-cell grid, including both shunts.
Private acceptance files: `insertion-combined-{review,result,final}-20261006.json`.

Production insertion is limited to contiguous, fully verified serial display
row3 with Amp1/Cab1 and enough actual empty columns at the right edge.
Only Drive1, Compressor1 and the previously verified Chorus1 may be added.
Drive/Compressor precede Amp; Chorus immediately follows Cab. Existing effect
order is preserved. Every displaced block/shunt, every cable and all original
settings are independently checked. The FM9 read-only splice planner is
reused when it would not spend a shunt. Otherwise TC displaces the entire
span to real empty slack, retaining each shunt. No shunt is overwritten.
Parallel layouts, full grids, unsupported additions and ambiguous aliases
are refused before writes. Partial failure stops and remains an unsaved edit.

The text compiler exposes optional missing Drive/Compressor as ADD actions,
using the requested captured model or T808 OD/Modern VCA defaults. Newly
added blocks are bypassed in configured scenes that omit them. Omission
still preserves an existing effect. Missing GEQ/PEQ remains unsupported.
New numeric writes require ADD, explicit channel and captured model first;
orphan modifier records targeting an absent new block refuse the whole plan.
Physical mute is mandatory; there is no calibrated limiter or acoustic match.
This insertion-only test preserved amp/cab voicing; a new full text design
may intentionally change those sounds, so review the entire proposal.
Hardware insertion/configuration acceptance is scene1/channelA. A-D design
and other geometries are covered offline, not asserted as heard presets.

Final SIM regression run: **750 passed**, 116.32 seconds, six workers.
Includes all AFX3 tests, mandatory device-handle/capability/UI-warning,
invariant safety and unchanged FM9 splice/consent regressions. Report:
`insertion-final-gates-20261006.xml`. Real installed headless Chrome passed
the workspace and new unrequested-added-effect bypass summaries. The live
server was SIGTERM-restarted disconnected, then reconnected to323 with the
512-name User1 catalogue restored. No paid AI generation or sound audition
was used as evidence; this is protocol/application acceptance, not full FM9
effect parity or a proven recording reproduction.

## Offline and browser verification

Final 681-test run passed: all `test_axefx3_*.py`, the mandatory device-handle,
capability and UI-warning gates, plus invariant safety tests. Report:
`effects-final-gates-20261006.xml`. Installed headless Chrome passed the
scene table (including new controls), retained request, newline, consent,
failure, XSS and mobile checks. The HTTP review/executor path is also tested
offline for all four optional families.

A freshly built and isolated-installed Python wheel loaded all 75 registry
controls, the new design schema and numeric pid-0 frames without MIDI.
The existing wheel packaging does not contain UI assets; source-tree UI
verification is separate and this is not a proven standalone installer.
