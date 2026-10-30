# FX3 adapter FW33/NAM port

## Profile warning, 28 October 2026

The acceptance below is retained evidence for the earlier exact
`33.00-beta.20261006` profile, not a current Beta5 feature list. See the
[capability matrix](AFX3-CAPABILITY-MATRIX.md) and
[Beta5 migration](AFX3-FW33-BETA5.md) before testing a newer build.
No older successful test is removed or silently promoted to another firmware.

## Current acceptance, 2026-10-18

The sections below record successive historical checkpoints, not a single
current feature list. Current support includes336 amps,2048 Factory cabs,
User1/2 catalog addressing, four-slot cab mixing, measured1..8-scene AMP/CAB
builds and released T808 Mod, Modern VCA and10 Band Variable Q voices. New
measured Amp/effect scalar zeros and automatic verified Tempo NONE on reviewed
AMP/CAB timing pass native, normal SEND and independent editor acceptance.
See [zero/timing scope](AFX3-ZERO-TEMPO.md), the
[seventeen-item ledger](AFX3-COMPLETION-BACKLOG.md) and
[remaining work](AFX3-REMAINING-ACCEPTANCE.md). Wah1/2 source binding and
Off/Fast Pos Auto Engage now also pass native and independent editor checks
through the separate controller workspace. See the
[firmware migration inventory](AFX3-FIRMWARE-MIGRATION.md) for retained legacy
functions and outstanding planner integration. This does not enable arbitrary
graphs, other controller targets, every effect model or other firmware/chassis/platforms.

## Earlier port baseline

This integration port uses the owner's inspected 939e3ef implementation and
historical muted Axe-Edit 1.15.01 comparisons. It is not new hardware acceptance.
The exact firmware identity is `33.00-beta.20261006`; raw 97.00, a different
date/checksum, FW33 final or a later beta does not enable it.

- 36 first-instance numeric controls: Amp8, Wah9, Delay4, Reverb3, Chorus4,
  Compressor2, Output1, NAM5. SET divisors/opcodes come from measured data.
- Exact zero only for Delay/Reverb/Chorus Level and NAM Input Gain/Level.
  Positive dB gain/levels and feedback over 60 percent are blocked. This is
  not a physical-volume limiter. Literal delay/chorus timing requires NONE
  independently read before writing, with no guessed FW33 tempo setter.
- NAM effect206 is separate from Chorus78 in full eight-bit grid decoding.
  The NAM route Input1 -> NAM1 -> Cab1 -> Delay1 -> Chorus1 -> Reverb1 -> Output1
  is buildable from a truly empty preset, scene1/A. A separate captured
  one-scene14-block Amp/Cab serial template is described below. Neither
  enables arbitrary chain placement. An existing exact NAM route may
  use scenes1/2 and NAM A/B; other blocks stay on shared A. No splicing,
  arbitrary model/CAB/mixer or modifier writes on FW33. The separately measured
  NAM slot selector is described below; it does not enable amp/effect models.
- Native NAM read/install: Windows, user-declared MK2, exact firmware and
  slots001-256 after explicit destination confirmation. Existing supported
  48kHz SlimmableContainer v0.7 A2 geometry
  with 1871/12146 finite weights. No downloaded code or Axe-Edit required.
  A creator's A2 label alone does not prove this geometry or tonal quality.
- Install is separately permanent: local browser-CSRF boundary, three strict
  acknowledgments, single-use ten-minute preview, fresh target/old hash,
  verified private recovery export, separate narrow traffic guard, complete
  65536-byte readback. Ordinary input is handed off to WinMM and reopened in
  finally. Unsupported MIDI backends decline before releasing input.
  Reconnection, profile, selected-model or memory changes invalidate approval;
  a matching slot hash on a different connection is not installation consent.
  NAM memory is shared: replacing a slot also changes other stored presets
  that reference it. An empty target does not prevent that effect; those
  references are not inventoried automatically. Review the overwrite warning.
- Inventory reads all256 names serially and suggests the first explicitly
  empty slot. A missing/malformed reply aborts inventory, not guessed emptiness.
  Selected destinations are independently exported in full before preview and
  again before commit; complete erased65536-byte memory is the empty state.
  Changing the target invalidates browser consent; the single-use token binds
  the actual slot and old full-memory state. A full bank requires a deliberate
  occupied-slot choice, never an automatic overwrite. This installs a capture
  in memory, not an implicit selector change in a preset. Explicit installed
  capture selection uses a separate state-bound reviewed preset plan.
- Store is separately permanent and reviewed, same current allowed preset,
  exact captured 23-byte command and settled flash-name readback. No Store As,
  automatic reload, rollback or implicit writes from an AI recommendation.

Historical preset326/slot001 test on 2026-10-08 and owner listening acceptance
on 2026-10-09 apply to the previous installation, not automatically this port.
Before deploying this integrated adapter: new identity/read-only check, muted
test-preset writes, independent Axe-Edit comparison, separately authorized
NAM/Store validation and low-volume user listening/physical pedal acceptance.
The offline phase ran with the Fractal off. Subsequent muted native TC API
tests on2026-10-09 installed the selected supported capture in authorized
slots250 and256 with full65536-byte hash verification and valid recovery
exports; NAM001 and the complete stored reference326 state stayed unchanged.
Independent Axe-Edit NAM manager confirms the names at250/256 without import
or Save; Axe-Edit is not the installer.
The name inventory reads all256 slots in both populated and empty preset
contexts. Address requests were independently captured from Axe-Edit before
native writes. Source and browser tests are not physical sound acceptance.
Remote GitHub CI and hardware regression are recorded separately. Ordinary pip wheels remain
unsupported as complete apps under upstream's resource policy; use the source
checkout/editable installation until a bundled distribution passes its own run.

## Explicit GUI navigation acceptance, 2026-10-09

Click the preset header to search freshly read preset names000-511; click a
named scene button to select scene1-8. The connection indicator says VERBONDEN
only when TC reports a connection. Names/status reads do not select anything.
Navigation has separate expiring, single-use, device/state-bound confirmation.
External mute is required; loading a preset additionally requires acknowledging
that unstored device edits will be discarded. Request text stays in the GUI,
but previous build approvals are invalidated. Navigation never performs Store.

The native exact-FW33 test selects all eight scenes on325 and presets324/325,
then compares complete325 state with its baseline. The actual browser reads
all512 names, selects scenes1/8/2 and presets324/325, verifies consent and
retained text, and checks1180/1280/1440 layouts without JavaScript errors.
No parameter, model, NAM-memory or Store writes are part of this test.
Scene selection has an exact one-operation frame permit; it does not extend
AI NAM builds beyond their measured scene1/2 scope. Generic automatic preset
reload, unknown firmware and arbitrary model/routing/controller writes remain
blocked. This native/browser result is not an independent Axe-Edit comparison
or physical loudness measurement. Test switching stayed within321-329;
other preset banks are not claimed as newly hardware-tested.

### Next independent FW33 measurements

FW33 model/CAB selection, free grid construction and new modifier allocation
remain deliberately disabled. This is not just a product-code difference:
the32.06 model roster/selection domains, CAB Legacy mixer layout and modifier
creation path are firmware-pinned. Identical-looking addresses are not new
readback proof. The current exact-FW33 grid permit covers only the accepted
NAM route. Human scene navigation does not extend that grid/build scope.

The next measurement pass needs an independently running Axe-Edit while TC
has explicitly released MIDI. First export a baseline of a test preset and
all32 modifier records, then passively capture a named AMP-model change, CAB
bank/slot change, isolated block/connection edit, and modifier creation/source
choice. After the editor closes, replay only the captured operation in TC
with external mute and compare full bulk/display/grid/modifiers, including
unchanged other channels. No globalCC mapping, firmware change or speculative
opcode is part of this work. A failure leaves the feature disabled.

The autonomous launch attempt was rejected by the execution environment before
execution. No editor was started and no blocked operation was retried through
another mechanism. A user-opened editor is required to resume this independent
measurement; native/browser navigation tests already completed without it.

## NAM player-selection acceptance, 2026-10-09

This chooses a capture already installed in memory. It never downloads,
installs or overwrites shared memory. Explicit request field `nam_slot` selects
the design capture; omission preserves the current NAM channel's capture, not
an implicit001. The request widget lists occupied slots from complete inventory.
Review shows the actual slot/name; failed inventory clears old choices. Install
and in-preset selection remain distinct, separately reviewed operations.

- With TC stopped, the user selected250 ->256 ->250 in Axe-Edit NAM Player1/A
  on preset328. A passive observer captured checksum-valid opcode09 parameter0
  frames with float32 ordinals249/255/249. Incoming buffers were unavailable
  to that observer; no incoming trace/readback is claimed. The visible editor
  showed250. Subsequent exclusive TC bulk independently returned249 at offset0
  in the complete four18-word NAM channel layout.
- After the editor closed, TC replayed256 and250 under a verified muted edit
  session, bypass and quiet-level staging. Complete bulk confirmed each ordinal
  and unchanged other channels. Full65536-byte NAM001/250/256 memories were
  checked before/after and unchanged. A changed selector stays quiet/bypassed
  until the reviewed design explicitly voices and engages that channel.
- Choices001-256 use the measured ordinal encoding, constrained to NAM
  Player1 and exact MK2/FW33. Hardware replay used001/250/256, not256
  destructive tests. A later user-operated256 ->001 ->256 ->001 measurement
  on329 captured opcode09 zero twice. Visible editor selection001 and complete
  independent TC bulk ordinal0 confirm the final selection. Native TC replay
  256 ->001 ->250 ->001 independently verifies each selection, complete
  unchanged NAM001/250/256 memories, unchanged other NAM channels, other block
  bulks and grid. NAM remains quiet/bypassed. No Store or installation occurs
  in that selector-only pass. Channels A/B remain the reviewed build scope.
- The previous technical AI design is then recompiled for001, reviewed and
  sent through the actual registered API:60/60 actions, zero skipped. Both
  NAM A/B select001. Separate Store329 and diagnostic reload reproduce the
  full state; stored326 and NAM001/250/256 remain unchanged. This is not a
  new paid AI or sound-matching test. Mandatory and changed regression tests:
  268 passed. Graceful runtime restart loads the new code on the single8909
  instance; live state independently shows NAM001 on preset329/scene2.
- Actual registered API, live adapter and configured Codex build one-scene
  preset329 using250:41/41 actions verified. A second two-scene design uses256
  on NAM A/B:60/60 actions verified. This second request exercises the shared
  explained-rig reader and provenance report with pasted technical equipment
  text. It is not a live YouTube or listening test.
- Separate Store through the actual API succeeds. Diagnostic bank/PC switching
  329 ->328 ->329 reproduces complete state, including both NAM selectors,
  bulks, grid, modifiers, scene names and capture fingerprints. Stored reference
  326 and NAM001/250/256 are unchanged. Preset329 is `AI-NAM Slot Workflow`,
  two scenes. Cab is intentionally bypassed for this transport test, so this
  is not a complete tone or audible match. No automatic reload was enabled.
- Review/Store fingerprint the chosen full-memory capture plus all captures
  referenced by four NAM channels. Empty/incomplete chosen memory, changed hash,
  wrong slot, unknown channel or stale ticket refuses writes. Quiet staging,
  external mute and normal send consent remain mandatory. No generic selector
  frame is accepted without its exact one-operation permit. Ordinary FM9 guards
  and configured allowlists are unchanged.

## Actual YouTube, route exploration and NAM acceptance, 2026-10-09

The shipped GUI, actual selected Codex provider, encrypted TONE3000 account,
native installer and live MK2 adapter were tested with
[the user's Whole Lotta Love bluesrock reference](https://www.youtube.com/watch?v=Plwb_gfmSc4).
This is feature/transport acceptance, not a measured or audible recording match.

- Actual YouTube audio is downloaded and measured locally for60 seconds.
  The AI receives measurements, not isolated guitar or the raw recording.
  Exploration and planning reuse the same measurements for an unchanged
  source in the current browser session; changed URL/file/reset invalidates
  them. Browser tests cover repeat requests and changed-source isolation.
- Read-only route exploration considers AMP/CAB with pedals and NAM with
  effects. No route is silently selected. The user explicitly chooses an
  executable route; unsupported FW33 AMP/CAB remains a musical alternative,
  not a hidden NAM substitution. Detailed advice is separately collapsible.
  Real live catalog research using the short query `Whole Lotta Love`
  returns two candidates without selection, installation or preset writes.
- The direct song-related TONE3000 capture has a catalog name longer than the
  measured27-character ASCII header. Preview shows both names and adapts only
  the device label, not weights or compiler requirements. Native installation
  in authorized NAM252 verifies the complete65536-byte payload and keeps a
  verified private pre-write recovery export. No Axe-Edit is used.
- Empty325 builds the fixed NAM252 route with41/41 independently verified
  actions; a second actual GUI design extends it to Rhythm/Solo on NAM A/B
  with60/60 verified actions and zero skipped. The inventory is read again
  after refresh before selecting a numbered capture. No stale slot is reused.
- Separate GUI Store saves325 as `AI-Whole Lotta Love`. Diagnostic325 ->324
  ->325 reload reproduces the complete snapshot: grid, bulks,32 modifiers,
  both scene names, capture fingerprints and NAM252 on A/B. Stored reference
  326 and full NAM001/250/251/256 payloads remain unchanged. An earlier
  fallback JCM800 capture was separately installed in251 and its one-scene
  test remains stored on328. These are authorized test resources, not a
  product requirement to overwrite them or depend on Axe-Edit.
- Fresh numeric checks on saved323 independently verify Amp Drive/Bass/Mid/
  Treble/Master/Depth/Presence/Level, Compressor Threshold/Ratio and Output
  Level. Amp model, other channels, other block bulks, grid and modifiers stay
  unchanged. Diagnostic reload restores the entire saved323 baseline. This
  accepts existing measured numeric setters, not FW33 amp model/CAB selectors,
  controller bindings, extra block construction or complete FM9 parity.
- Final Windows SIM regression:4,426 passed,16 skipped,336.23s,eight workers.
  Fresh mandatory/changed regression:350 passed,128.12s,four workers. Real
  Chrome with shipped assets passes explicit route choice, cache reuse after
  request/NAM-search changes, changed-source invalidation and text safety.
  Actual live compact GUI/provider/catalog regression also passes. Public
  staged-file release tripwire passes; remote CI and manual review are not
  substituted by these local checks.

Native install still requires supported capture geometry and exact firmware.
Arbitrary routing, CAB/model writes and controller bindings on FW33, physical
audition and remote CI remain separate pending work. Axe-Edit is a comparison
tool, not a dependency of the native installer or preset writer. Local traces,
model files, private recovery exports and reports stay untracked.

## Free-grid measurement checkpoint, 2026-10-10

The user-operated Axe-Edit measurement was made on preset324 under external
mute. This preset has a nonempty parallel rig despite its EMPTY name. The
original rig and its wah/volume modifiers were preserved; two test blocks
were placed separately on the empty fifth row, not connected to the output.

- Exact outgoing frames capture Compressor1/Drive1 placement, their cable,
  cable removal and both deletions. The cursor is encoded independently of
  the insert payload. Captured insert payload positions differ from the
  selected target; do not silently substitute a calculated insert position.
- The cable add/remove bytes match the shared FM9 builder for this geometry,
  with the FX3 envelope and checksum. This does not establish every coordinate
  or block type, nor remove the shared builder's undecoded-coordinate limits.
- Native TC repeats ten exact captured frames on324 with a developer-only
  permit. Every step independently verifies the full grid and complete original
  block bulks, status,32 modifiers, scene names and referenced NAM memory hash.
  Final complete state equals the baseline. No Store, model/level write,
  installation, global mapping, move or automatic rollback occurs.
- After the native connection was released, the user reopened Axe-Edit.
  Independent visible-grid inspection confirms the original parallel route,
  block channels/bypass state and empty fifth row. The editor was not used
  to apply or save TC's native test writes.
- The fixture guard requires exact firmware, a muted preset-bound edit session,
  fresh selection, absent insert target, expected block identity and isolated
  cable/removal state. Other cells and presets remain blocked. This is not an
  AI action, HTTP endpoint or public deletion/parallel-build capability.
- New read-only topology checks preserve branches and fan-in instead of
  flattening them. Every cell must lie on a complete Input1-to-Output1 path.
  Dangling cells/cables, ambiguous status, malformed masks, multiple IO and
  feedback-capable blocks are rejected; physical loudness is not verified.
- Mandatory device/capability/UI-warning and changed-module regression:
  237 passed. After additional transport refusal tests, the final focused
  adapter/grid/topology regression passes187 tests. These are local Windows
  synthetic tests, not remote CI or sound-match acceptance.

Remaining promotion gates: independently measure other block-placement frames,
supported cable geometries and safe branch/move operations; verify each native
operation; then add a state-bound graph review and executor/GUI integration.
Current public FW33 builds remain confined to the accepted NAM route. Numeric
and model/controller availability remain separate from topology capability.

### Subsequent diagonal measurement and graph planning

The owner subsequently placed Compressor1 at row5/column1 and Drive1 at
row6/column2, connected them diagonally, removed the cable and deleted both.
The passive trace captures all ten operations with valid FX3 checksums. The
insert payloads are identical to the earlier fixture despite the different
Drive cursor position. Cable add/remove matches the shared FM9 builder for
this geometry. No incoming trace buffers are claimed.

After the user closed Axe-Edit, TC natively replayed all ten exact frames on
324. Full grid and every original block bulk, status,32 modifier records,
scene names and referenced NAM hash are independently checked after each step.
Final complete snapshot equals the baseline, with no Store, model/level,
global or memory writes. Only this developer fixture is extended; free-grid
UI/planner execution is still gated. A later user-opened editor comparison
independently confirms the original324 rig and empty test rows5/6.

The next source seam is a read-only explicit graph contract. Proposed cells
use one-based positions plus a named block/instance or an explicit shunt;
cables name both adjacent endpoints. It refuses duplicates, undeclared cells,
missing paths, feedback blocks and incomplete device snapshots. The report
fingerprints the full baseline and lists differences and affected modifier
slots. A move remains a move with full-state preservation required; rewiring
around replaced nodes is reported even when cable coordinates are unchanged.
The list is not a safe transmission order, has no SEND token and cannot
authorize writes or overwrite blocks. Quiet staging and parameter/scene/
modifier preservation still need an independently accepted graph executor.

Actual read-only TC inspection of parallel324 verifies zero changes for the
identical graph and a three-operation extra Compressor branch proposal. The
proposal writes nothing and preserves the complete before/after device state.
The first read-only check exposed the real numbered, blank scene-name replies;
validation and regression now accept those complete replies, not invented
nonempty scene names. Private traces/reports remain outside Git.

Final mandatory device/capability/UI-warning plus changed adapter/grid/graph
regression passes286 tests on Windows, four workers. These tests do not promote
the proposed graph operations into general FW33 hardware capabilities.
Subsequent packaging/maintenance and graph/fixture regression passes107 tests.
A local wheel build includes all three new grid/graph modules and excludes
private KB/backups. This is a package-content check, not an installed GUI or
remote CI claim; the upstream wheel resource/startup boundary remains unchanged.

### Isolated movement round trip, 2026-10-10

After reopening Axe-Edit, independent visible inspection confirms the complete
original parallel324 rig and empty rows5/6 after the earlier diagonal native
test. A first movement capture is incomplete for its diagonal return and is
not promoted. A second user-operated measurement separately records right,
down, up and left between row5/column1, row5/column2 and row6/column2.

The native adapter then repeats the exact twelve-frame Compressor1 fixture:
insert, four separately selected moves and delete. Every step independently
reads the complete grid, original block bulks/status,32 modifiers, scene names
and referenced NAM hash. The Compressor's entire four-channel bulk and status
are identical before/after every move. Final full preset state equals baseline,
with no Store, model/level, global or memory write. The editor is closed before
native transport opens; no incoming passive-trace evidence is claimed.

The exact developer permit remains confined to324 and these isolated positions.
Fresh selection, the expected Compressor, an empty destination and no incoming
or outgoing cable are required. Unknown geometry, connected blocks, duplicate
identity, stale selection and raw/unreviewed writes are rejected. A failed
transport consumes the selection and permit without retry or automatic restore.
No generic move, shunt, branch execution, GUI/SEND action or firmware-wide
placement capability is enabled by this fixture. After native MIDI is released,
the user reopens Axe-Edit; independent visible inspection again confirms the
original parallel rig and empty rows5/6. Independent branch/shunt measurements
and general graph execution remain separate acceptance steps.

Mandatory device/capability/UI-warning plus changed adapter/grid/graph tests
pass292 cases on Windows, four workers. This is a local synthetic regression,
separate from the real12-frame movement replay and editor comparison above.

### Complete row references, 2026-10-10

The owner separately designates320 for measurement and starts from an empty
grid. Left-to-right placement records Input1, Wah1, Drive1, Amp1, Cab1,
Chorus1, Compressor1, Delay1, Enhancer1, Filter1, Flanger1, GEQ1, PEQ2 and
Output1 on row1. Row2 has fourteen shunts. Each row has thirteen serial cables;
row2 is intentionally detached and is not a playable complete signal path.

All82 relevant outgoing selection/insert/connect frames match the retained
reference. Screenshot and main-grid UIA confirm28 cells; Quick Build palette
entries are excluded from the actual grid. After the owner closes Axe-Edit,
native read-only inspection independently verifies every effect ID, shunt and
cable mask, including all26 connections. All14 full four-channel block bulks,
32 modifier records and eight scene-name replies are read. Two complete native
snapshots are identical, with no write or Store. Exact firmware remains
33.00-beta.20261006; the on-screen shortened version alone is not sufficient.

Twenty cables match the existing shared FM9 builder exactly. Six row1 cables
from even columns are explicitly undecoded by that shared builder; the actual
FX3 frames are retained literally, not generalized to other coordinates or
promoted into FM9 hardware support. Shunt INSERT IDs1024-1037 and payload6 are
retained as observed in this sequence. Effect INSERT payloads are distinct
from their separately selected grid cursor positions.

The reference alone does not authorize writes. Ordinary FW33 transport and
public graph-write capabilities remain blocked for these frames. Existing
scene, model, parameter, feedback and storage guards are unchanged.

### Exact two-row native round trip, 2026-10-10

A separate user-operated removal capture records all26 cable disconnects and
28 selected deletions. Its82 frames exactly match the removal reference.
Read-only main-grid UIA confirms all84 positions empty afterwards. The owner
closes Axe-Edit and reconfirms external audio muted before native execution.

A developer-only probe starts from empty320, exact FW33 MK2 and a confirmed
edit session. Every step is tied to the captured ordered frame and a freshly
read whole-grid prestate. Writes settle, then independent grid reads verify
the entire expected poststate. An exception, mismatch or changed target
consumes the probe; no unknown write retry or automatic restore. Its temporary
permit enables only this164-frame sequence, not an AI/API/SEND capability.

Actual native execution verifies28 placements,26 connects,26 disconnects and
28 deletions, with56 cursor selections. After each of the108 grid mutations,
complete native snapshots verify all existing four-channel block bulks/status,
32 modifiers, eight scene-name replies, preset/scene identity and referenced
NAM memory hash. Both constructed rows match the independent Axe-Edit/grid
reference. Final complete state equals the original empty baseline. No Store,
model, level, global or NAM/IR memory write is sent. Newly inserted blocks use
their device defaults; this is not restoration of deleted musical settings.

Mandatory device/capability/UI-warning and changed adapter/grid tests pass309
cases locally; another86 graph, topology, packaging and maintenance tests pass.
These synthetic tests are separate from the actual native replay. After native
MIDI is released, the owner reopens Axe-Edit; independent screenshot and UIA
inspection confirm320 and all84 main-grid cells empty. Branch/fan-in measurements,
general state-bound graph execution and GUI/SEND integration are still needed
before public free-chain construction. No musical or physical loudness proof.

### Detached parallel native round trip, 2026-10-10

In a separate owner-operated320 capture, Compressor1 is at row5/column1,
Drive1 at row5/column2 and two shunts at row6/columns1 and2. Each source in
column1 connects to both destinations in column2. Main-grid screenshot/UIA
confirm all four cells and visually all four cables. The actual drawing order
is both horizontal cables first, then downward and upward crossings. Removal
is a separately measured order, not inferred from the requested instructions.
All24 relevant select/insert/connect/disconnect/delete frames match exactly.
All eight routing literals also match the unchanged shared FM9 builder for
these specific measured coordinates. No general routing formula is promoted.

The same bounded320 developer probe has a second fixed mode for this exact
sequence. Its native replay independently reads every intermediate grid and
full preset snapshot. Both destinations have cable mask96 (source bits32 and
64); disconnecting one cable preserves the other source bit until explicitly
removed. All four-channel Compressor/Drive words and status,32 modifiers,
eight scene-name replies and referenced NAM hash remain unchanged. Final full
empty state equals baseline. No Store, model/level, global or NAM/IR memory
write. Native MIDI is released before the owner opens the editor again.
Independent screenshot/UIA confirms320 and all84 main-grid cells empty.
This detached measurement is not a complete playable rig,
musical proof or parallel mixer/headroom verification. General graph/SEND
integration remains blocked until its own state-bound execution acceptance.

Mandatory device/capability/UI-warning plus changed adapter/grid/fixture tests
pass334 locally, and86 graph/topology/packaging/maintenance cases also pass.
Native acceptance above is recorded separately from these synthetic results.

### Broad first-instance reference, 2026-10-11

The owner builds321 using Axe-Edit Quick Build under confirmed external mute.
Separate passive recordings capture41 placements and37 explicit grid cables,
then37 disconnects and41 freshly selected deletions. All checksums are valid.
Screenshot and84-cell main-grid UIA match the complete construction and later
empty grid. Native read-only inspection independently confirms all41 effect
IDs, positions and cable masks, all complete block bulks,32 complete modifier
records, eight scene names and referenced NAM memory. Two full snapshots are
identical. Dynamic Distortion202 and NAM206 retain full identities, not aliases.

The reference includes two Feedback Send/Return pairs and Output2-4. One cable
is missing between Reverb1 and Send2 on row2. Neither implicit feedback pairing
nor a complete playable route is inferred from the picture. The owner reports
saving the populated321; TC does not Store, reload or overwrite that reference.
After separate removal, native inspection confirms an empty321 work buffer.
Explicit selection of owner-designated322 confirms that test target is empty.
No automatic rollback, NAM install, global or firmware change is performed.

`block_probe.py` defines a developer-only isolated322 sequence for34 observed
blocks, excluding all four Send/Return blocks and Output2-4. Each block is
selected, inserted with its literal captured payload, reselected and deleted
before the next type. There are no cables or model/parameter writes. Exact
firmware/MK2, an empty baseline, a confirmed edit session and a freshly read
whole-grid prestate are required. A failure consumes the probe and its permit;
there is no uncertain write retry or restoration. This is not an AI action,
HTTP endpoint, generic block-placement capability or parameter-voicing proof.

Native execution on322 completes all136 ordered frames:34 isolated placements,
34 deletions and68 selections. Each step verifies the whole grid; each created
block is read twice with its complete bulk/status, including after reselecting.
All bulk lengths match the independent populated321 reference. After each
deletion the entire empty preset state equals baseline, including32 modifiers,
eight scene names and referenced NAM hash. The final complete state also equals
baseline. No cables, model/parameter/level, Store, global or NAM/IR memory writes.
Native MIDI is released. A subsequent owner-opened Axe-Edit322 screenshot and
84-cell main-grid UIA independently confirm every cell empty.
Synthetic mandatory device/capability/UI-warning plus changed tests pass357
locally; another86 graph/topology/packaging/maintenance tests pass. These are
separate from native results, not remote CI or audible/headroom acceptance.

### Complete serial developer construction, 2026-10-11

The same322 developer boundary has a separate fixed chain mode. It reuses
only the previously captured14-block row1 reference, not invented coordinates:
Input1, Wah1, Drive1, Amp1, Cab1, Chorus1, Compressor1, Delay1, Enhancer1,
Filter1, Flanger1, GEQ1, PEQ2 and Output1. Fourteen selected placements plus
thirteen serial cables make41 grid commands. Exact order and fresh complete
grid pre/post states are checked, with no feedback or extra outputs.

The first native harness stops after the last independently verified INSERT,
before any cables or output-stage write, because its test-only parameter
lookup used the wrong Python call signature. The incomplete report is retained.
No insertion is retried. A new full read verifies the exact14-block uncabled
state and all preserved baseline fields, then a separate fixed connection-only
mode sends the thirteen previously unsent cable frames. It accepts only this
known uncabled state, not an arbitrary partial graph or resumption index.

Output1 uses the existing verified setter at-18dB before connecting. Independent
display/bulk confirms that only its channelA level word changes; other output
channels and all other blocks remain unchanged. Every connection subsequently
verifies all complete block words/status,32 modifiers, eight scene names and
referenced NAM hash. Native serial-route and graph checks confirm14 nodes,
13 edges and a complete Input1-to-Output1 route. Two final full snapshots match.
There is no Store, model change, NAM/IR installation, global or firmware write.

Native MIDI is released. A subsequent owner-opened Axe-Edit322 screenshot and
84-cell main-grid UIA independently confirm all14 expected blocks in row1;
the screenshot also shows all13 serial cables. The remaining70 cells are empty.
The un-stored technical chain remains on322. It is not a voiced musical preset or evidence
of physical loudness, bypass transparency or controller operation. The-18dB
output is not a limiter; external audio must remain muted for this test.
No public AI action, graph execution endpoint or arbitrary FW33 build support
is promoted by the fixed developer modes. Their own GUI/executor integration
and independent tests remain separate work.

Final mandatory device/capability/UI-warning plus changed tests pass373 locally;
another86 graph/topology/packaging/maintenance tests pass. These synthetic runs
do not replace the native and independent editor evidence above, or prove
remote CI, audible tone, safe physical volume or general graph execution.

### Reviewed serial template, 2026-10-11

A separate production module, `serial_build.py`, reuses only the exact captured
14-block row1 sequence. It is not the developer probe, a generic coordinate
formula, free graph editing or destructive replacement. A truly empty preset
can be built; an existing exact row1 chain can be voiced without grid writes.
Incompatible, partial, moved, parallel or controller-active states fail before
execution. No automatic scene/channel switch, write retry, clearing or reload.

The explicit GUI choice is `AMP / CAB: gemeten testketen`. The selected AI uses
the bounded one-scene schema in `serial_planning.py`. Amp/Cab models and IR
mixers stay existing/default; no claimed artist-model or original-rig match.
Only measured Amp numeric voicing, Delay and Chorus are configured. Wah,
Drive, Compressor, Enhancer, Filter, Flanger, GEQ and PEQ2 remain bypassed.
PEQ2 has placement/identity evidence, not writable parameter evidence.
Reverb, model/IR selection and new controller bindings are not enabled here.

All41 grid frames use ordered single-operation permissions, confirmed target,
whole-grid pre/post checks and complete state preservation. Output and Amp are
independently staged to-18dB before connecting; only their channelA level words
may change in staging. Full block words/status,32 modifiers and eight scene
names are checked throughout construction. Delay/Chorus layouts and Tempo NONE
must be independently read before cables; no speculative tempo setter.

The normal review uses complete fingerprinted state and an expiring one-use
token. SEND still requires target and external-mute acknowledgements. This AMP
template's plan/review/SEND/state do not require a NAM capture or account.
The existing NAM build and shared FM9 planner/transport remain unchanged.
Channel and bypass metadata are read from hardware for GUI route badges;
white bypass labels have red channel borders, not an inferred active state.

Native acceptance on authorized empty323 uses actual configured Codex and the
registered planning/review/SEND APIs, not mocked AI or a developer probe.
Planning writes nothing. SEND completes46 actions with zero skipped, all14
nodes and13 cables, scene1/A and independently verified17 numeric displays.
Amp gain5.5/level-18dB, Output-18dB, Delay320ms/20%feedback/18%mix and Chorus
0.7Hz/25%depth/12%mix are read back. Reserve effects are bypassed. Complete final
state is stable;32 modifier records, scene names2-8 and full NAM001/250/256
hashes stay unchanged. No preset Store or model/IR/NAM/global/firmware write.

Independent owner-opened Axe-Edit comparison of this new normal-SEND preset323
now confirms all14 first-row blocks, channelsA, the eight bypassed reserves
and70 empty cells. The inspected screenshot shows all13 serial cables,
AI-Serial Acceptance and scene1 Crunch. Native masks provide the exact cable
proof; this read-only UI comparison neither opens MIDI nor performs Save.
Chrome with shipped assets and mocked APIs passes explicit
serial choice, one-scene limit, no NAM selection, review/confirmation, actual
bypass badges and old-backend compatibility. This is not yet an actual live
browser AI/review/SEND acceptance, an audible tone match or remote CI.
After the owner closed Axe-Edit, the single updated runtime on8909 was started
normally with the existing owner AI/preset-policy files. Actual live Chrome
reads preset323/scene1, all14 channel badges and eight bypassed blocks, verifies
white labels/red borders and the explicit serial option. Route selection still
requires the normal request and AI route exploration; that gate is not forged.
The live GUI check performs only GETs and local form changes, no AI call,
navigation, SEND, Store or installer action. Native selected-AI/SEND evidence
remains the separate registered-API acceptance above.

Final mandatory device/capability/UI-warning and changed regression suites
pass421 locally after the completed-sequence and incompatible-state guards.
The real Chrome mocked-API workflow also passes after those source changes.
No hardware replay or remote CI is inferred from these local checks.
The full simulator regression for source checkpoint75cf939 passes4733 with16
skips in507.01s using four workers. The local wheel builds and contains both new serial
modules; this does not change upstream's unsupported wheel GUI/resource policy.
The subsequent long-chain layout follow-up starts the scrollable bar at Input
instead of clipping the leading blocks through centered overflow. Both ends
are separately tested in mocked and live Chrome at1180/1280/1440px.
Post-layout mandatory device/capability/UI-warning tests also pass54 locally
in119.72s. No remote CI, audible match or arbitrary grid editing is claimed.

### Eight-scene planning preparation, 2026-10-11

The normal request schema now accepts1-8 scenes. This is request capacity,
not proof of eight-scene execution on FW33. The FW32.06 AMP/CAB compiler can
allocate up to four different stored configurations per block across eight
scenes. It never derives a block channel from scene5-8. Exact identical
settings can share A-D; bypass remains per scene. Amp model and voicing are
part of the sharing key, as are complete Cab IR pairs and effect settings.
A fifth different configuration is refused before review. No approximation,
silent overwriting, extra Amp instance or guessed selector is substituted.

Four album pairs can use four amp voices and differentiate solos through
effect bypass and output levels capped at-6dB. The compiler writes each shared
configuration once. Legacy1-4-scene independent amp/effect assignments remain.
Optional scene model/IR overrides permit distinct album choices from the
verified firmware/catalog; names alone are not device availability proof.
The review displays actual channel allocation, per-scene IR names/banks and
output levels. Old backends and narrower FW33 modes retain their GUI limits.

FW33 AMP/CAB rejects these requests with a profile-specific explanation before
AI, NAM-memory reads or execution. It no longer returns a misleading generic
four-scene schema error or recommends a forced NAM replacement. FW33 NAM
remains limited to its independently measured1/2-scene contract, and the
measured serial template remains1/A. Selector/channel/mixer and final native
eight-scene construction, independent Axe-Edit comparison and Store/reload
acceptance are still required. No preset326/327 was built or stored by this
software-only phase. Simulator/Chrome results do not promote FW33 support.

Local regression passes345 mandatory/changed tests and260 additional model,
Cab, profile, firmware, maintenance and packaging tests. Shipped GUI assets
pass real Chrome with mocked APIs, including eight rows, A-D allocations and
continued narrower FW33 limits. These are not native eight-scene acceptance.

An actual selected-AI/registered-SEND preparation on empty authorized328
creates AI-FW33 Model Test with46 independently verified actions, scene1/A,
the existing measured14-block template, Amp/Output-18dB and Delay/Chorus off.
It is only a temporary model/channel measurement foundation. No selector,
Store, NAM-memory write or Metallica326/327 build occurred. This avoids asking
the owner to rebuild a chain by hand; independent selector/channel comparison
still remains necessary before enabling the new FW33 album execution route.

### AMP channel measurement, 2026-10-11

The owner-operated Axe-Edit capture on328 changes Amp1A and Amp1C to
Brit8002204High, then returns through B/C/D/A. The final independent editor
screen shows channelA and Brit8002204High. Native read-only inspection confirms
four142-word amp channels with model ordinals14/267/14/267 and a stable full
14-block route. Only the A/C model writes were emitted; B/D model selection
was unchanged. This capture does not establish a writable ordinal267 selector.

The editor uses internal subcommand0x16 with raw channels1/2/3/0 here, rather
than the shared FM9 FN_CHANNEL command. A separate fixed developer probe
replays only those four literal commands on328, with a confirmed muted edit
session, exact chain, inactive modifiers, existing Output1 attenuation-18dB,
fresh complete state and single-use frame permissions. After every command,
native status and full block words verify that only the current Amp1 channel
changed. Final complete state equals the baseline, with no model, parameter,
grid, controller, NAM-memory or Store write. Post-replay independent editor
comparison confirms the complete chain and final channelA. No normal planner/GUI channel capability, general
model roster or eight-scene FW33 execution is enabled by this probe.

### AMP model and numeric calibration, 2026-10-11

After explicit owner authorization for autonomous editor operation, a fresh
recording on328 captures model267 (USA JP IIC+ Yellow), model14 (Brit8002204
High), bypass and eight numeric controls on each of B/C/D. The final editor
state is independently read twice through the native adapter. There are568
amp words, four142-word channels, no active modifiers and Output1-18dB.
The passive observer captured outgoing frames only; it is not inbound proof.

A separate fixed developer calibration executes58 literal steps: two model
changes onA, channel navigation,24 numeric changes across B/C/D, then24
restoration writes and a return toA. Amp stays bypassed throughout. Every
numeric step verifies its independent display and exact addressed bulk word,
with all other state preserved. A model change can reset only its own channel's
142-word voicing; the other channels, route, status, modifiers and names must
remain unchanged. Unknown outcomes consume the calibration without retries
or automatic rollback. No Store, IR installation, NAM-memory or global write.

After native MIDI release, a newly opened Axe-Edit independently confirms the
two models and all eight controls on A/B/C/D, then returns toA. B-D are back
at their original editor-calibrated values. Gain/EQ/master/depth/presence SETs
first round the display input to float32 before division by10, matching all24
recorded numeric literals. The former Python-double path differs by one packed
ULP for some values. This correction establishes frame fidelity; it is not
evidence of an audible difference or the cause of earlier weak guitar tones.

The calibration remains a developer operation, separate from normal SEND.
The bounded album contract below records its own selected-AI/SEND, independent
comparison and Store/reload acceptance. Listening remains a user check.

### CAB Legacy IR1 measurement, 2026-10-11

Owner-authorized editor recording on328 independently identifies Factory2
slot516, 4x12 Brit70s GB57A, and slot800, 4x12 Recto57A. Their wire ordinals
are515 and799; bank1 selects Factory2. A separate changed selection of the
Factory1/Pig slot1 records exact-zero bank and slot SET09 literals. No IR file
is installed. Cab channel B/C/D/A uses the captured internal0x16 commands.

The custom editor picker can expose underlying UIA buttons. An initial
measurement-helper overlay mistake selected a different IR1, Factory2 slot841,
on328. It was not stored or accepted as a planner choice. Native read-only
comparison proves that only CabA bank and IR1 ordinal changed; complete other
state stayed intact. The helper now requires unobscured grid/sidebar pixels
before opening a picker and validates the specific IR1 name/bank/slot afterward.
This is a local developer UI helper correction, not a change to TC's GUI.

A fixed developer probe starts from that independently established baseline
and performs21 captured-literal native steps. Bank/IR1 choices and current
Cab channel are the only allowed changes. Four106-word Legacy channels are
required; other IR selections, level/pan/mute words, route, amp, modifiers and
names are preserved after every step. The final CabA/C IR1 is Greenback516,
CabB/D IR1 is Recto800, all in Factory2. Amp remains bypassed and Output-18dB.
Failures consume the probe without a write retry or automatic rollback.

A freshly opened Axe-Edit independently confirms all four IR1 names, displayed
bank/slot and unchanged mute control pixels: IR1 in mix, IR2-4 muted. It returns
toA. This is selection and preservation proof, not a stereo-panning, measured
loudness or audible-match claim. Neither the testpreset nor shared IR memory
is stored. Normal planner selectors, arbitrary IR ordinals, mixer writes and
the eight-scene326 build remain separate acceptance gates.

A second native AMP pass changes both measured models on each of B/C/D and
restores all eight calibrated controls. All34 steps verify full state; final
complete state equals the baseline. After MIDI release, fresh Axe-Edit confirms
the models and controls on A/B/C/D and returns toA. The final mandatory and
changed simulator suites pass321 tests. This completes the bounded measurement,
not the normal eight-scene SEND, Store/reload or audible acceptance.

### Bounded eight-scene album integration candidate

The following records the historical paired-scene acceptance. The subsequent
general scene-goal and explicit A-D assignment workflow is documented in
[AFX3-SCENE-INTENT.md](AFX3-SCENE-INTENT.md). It keeps the measured model/IR,
route, safety and final survey boundaries, but does not require album pairs.

The normal AMP request has an exact MK2/FW33 eight-scene contract, separate
from the retained one-scene serial template and one/two-scene NAM mode. Four
album voices map to Amp/Cab A,A,B,B,C,C,D,D. Only Amp14/267 and Factory2 IR1
ordinals515/799 are enabled inside a reviewed ordered album session. Generic
model rosters/setters remain closed. Legacy IR1-only mixer state is required;
IR2-4 selections, levels, pan and mute are preserved, not manufactured.
Delay/Chorus each share A; effect models are retained. Output A is fixed-18dB.
The fixed14-block construction and every subsequent action preserve whole
device state outside the explicitly addressed field/channel. Unknown outcomes
consume the session without a write retry, alternate opcode or rollback.

An initial actual selected-AI/SEND test on329 verifies267 individual actions,
but a final scene survey finds that pre-transition bypass staging overwrites
the previous scene. That attempt is NOT eight-scene acceptance and was not
stored. The compiler now selects the new scene before bypass staging, under
confirmed external mute and already quiet A-D/output levels. Synthetic tests
persist real per-scene channel/bypass mappings, exposing regressions that a
stateless fixture misses. Corrected native acceptance remains pending here.

Separate same-slot Store review supports an album only after complete normal
SEND, with an unchanged full-state fingerprint on the same device connection.
Incomplete or stale builds cannot enable it. No automatic Store or reload.
The browser shows the bounded choices, all eight mappings and-18dB Output,
omits NAM-slot requests in AMP mode and preserves NAM/serial scene ceilings.

The corrected actual configured-AI/registered SEND on329 verifies267 actions
and an explicit native survey of all eight saved mappings, names, Amp controls
and IR selections. A fresh Axe-Edit then independently confirms all eight
scenes, four model/voicing channels, IR1 names/factory slots/mute pixels and
the complete84-cell grid. This test remains unstored; it is not a listening
or exact-album-tone claim.

The album contract additionally compiles eight explicit final scene-select checks
into SEND without rewriting the saved mappings. Its final fingerprint comes
from the executor's last independently verified state, not a new unverified
baseline. Separate Store reselects and verifies all eight scenes under the
explicit mute/permanent-write confirmation before sending Store. Hidden edits
to another scene therefore cannot evade a current-scene-only fingerprint.
Unknown zero FX values are excluded in the album schema; normalized numeric
bulk must match the requested display within one quantization word.
### Eight-scene preset326 acceptance, 2026-10-11

The actual configured AI chooses four distinct album voices and generates the
normal review for AI-Metallica albums on326. Registered SEND completes275
actions, including the final eight-scene verification survey. Native checks
confirm A,A,B,B,C,C,D,D Amp/Cab assignments, all eight saved names/bypass maps,
model/IR selectors, gain/EQ/master/depth/presence/levels and full preserved
grid, modifiers and other bulk words. Output A remains-18dB.

After MIDI release, fresh Axe-Edit independently confirms all eight scenes,
four model/voicing channels, IR1 names/Factory2 positions, IR1-only mute state
and the complete84-cell grid. It closes normally without Save or model/numeric
UI writes. TC reconnects and requires unchanged complete state before its
separate registered Store review and permanent-write confirmation. Store
verifies all eight saved scenes again, stores326, then the acceptance harness
explicitly reloads326 and checks complete state equality. The preset is saved
as AI-Metallica albums, ending on scene8.

KEA uses Brit800/Greenback; RTL uses Brit800/Recto; MOP and AJFA use distinct
USA JP IIC+ Yellow/Recto voicings. Each lead/solo pair shares an amp voice;
solos engage the shared delay, with chorus on RTL/MOP solos. Reserve blocks
remain bypassed. This verifies the bounded TC workflow and saved settings,
not an audible match to the albums or guaranteed physical loudness. Audition
at low physical volume. Arbitrary models, graphs, controllers, other FX
channels and CAB mixer writes are not promoted by this acceptance.

The single live TC on8909 also passes a real Chrome read-only GUI check:
preset326/scene8, eight names,14 labeled blocks, white bypass text/red channel
markers, the enabled AMP option and reachable Input/Output at three viewport
widths. No AI, SEND, Store or device selection is invoked by that GUI check.

Before the album commit, TONECOMMAND_SIM=1 mandatory contract/capability/
UI-warning and changed regression suites pass570 tests in246.49s. Real Chrome
mocked-API workflow tests also pass, retaining NAM/serial/consent/reset/source
behavior. Simulator and browser results supplement, not replace, the native
and independent-editor acceptance above.
