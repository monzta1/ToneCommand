# Axe-Fx III upstream integration

## Current source candidate, 2026-10-09

`integration/axefx3-upstream-20261009` now integrates upstream 1.5.14
(`c2dae138272cbfb26096ff7d92e643eacf8c32ab`) with the isolated exact FW33
NAM profile. See [current maintenance and release gates](AFX3-UPSTREAM-MAINTENANCE.md)
and [FW33 compatibility](FW33-COMPATIBILITY.md). The sections below are
historical FW32.06 milestones and are not acceptance of the refactored FW33 port.
The owner installation and successful audible preset remain untouched.

## Status: controllers accepted; bounded text workspace pending full hardware acceptance

Worktree: `integration/axefx3-upstream-20260929`, based on upstream
`3c97d6cff34c8b9ca842b79bed21154052411047` (1.5.4, merged 2026-10-01).
Source for the port: owner checkpoint
`18f8eac0b49820c8fb7c4248f76bfacacc6b6feb`.

This is a deliberate port, not a completed merge. The original installation,
private settings, cab imports and presets remain separate and unchanged.
The adapter can now be explicitly connected from the **controller workspace**
at `/controllers`. Reviewed Wah/Volume controller operations and a bounded
text-design workspace at `/axefx3` are exposed; the generic FM9 executor and
other device API routes remain blocked in this mode.
Installing this integration does not replace the owner's working application.
No publication or paid AI request is part of this work. Separately authorized
hardware checkpoints are recorded below. They do not prove full-preset tone
quality, arbitrary parameter coverage, or audio-reference matching.

The upstream gitignored knowledge base is absent. The owner explicitly
authorized continuing offline with public source/docs and the earlier fork's
evidence after being informed of that gap. No missing evidence has been
invented; the invariant safety guard and whitelists are unchanged.

## Why this is not an FM9 model-byte substitution

The framing/packing and parts of the Gen-3 read protocol are shared, but the
earlier catalog comparison found 492 named records with different parameter
IDs. Even within one AFX3 block, SET domains differ from displayed values
and from bulk-read normalization. The captured effect zero SETs also differ
from an FM9 generic ordinal-zero workaround.

`devices/axefx3` therefore has its own transport, registry, protocol boundary,
firmware-pinned evidence and package-local model data. It reuses only shared
packing, parsers, names/aliases, result types and the adapter contract. It
does not inherit `FM9`, mutate its protocol defaults or enable its automatic
global routing restoration/reamp path. Firmware 32.06 is the only writable
profile in this foundation; other firmware is read-only.

## What the newer upstream can contribute

The upstream amp sidecar contains exact-name factual metadata for 330 of
the 336 models in our FW 32.06 inventory. In this particular comparison their
ordinals also match, but `Registry.load_amp_facts` joins by unambiguous name,
never by ordinal. Six models have no
exact matching record and must not receive invented descriptions. These
facts (amp identity, intended cab, control layout) are useful reasoning
input; they do not authorize additional DSP parameters or model writes.

Upstream also adds cab identity/microphone metadata, per-scene recording and
measurement-driven balancing/tone-match modules. The pure measurement and
proposal code can be reused. The audio/device side cannot simply be enabled:
`fm9/reamp.py` selects an FM9 with 48 kHz, 8-in/8-out assumptions, and the
global routing/restore path is FM9-specific. Device-specific verification
must precede AFX3 audio capture or automatic level corrections. An analysed
reference alone still does not prove that the produced preset sounds alike.

The 2026-10-06 existing-effect checkpoint adds 32 Drive/Compressor/GEQ/PEQ
controls to the bounded text workspace, with 88/88 muted native TC writes
verified on TestPreset 323. See [core control evidence](AFX3-DRIVE-COMP-EQ.md)
for exact first-block mode gates, units, preservation checks and limits.
The follow-up verified 81/81 native model/control actions: Drive 1 Rat,
T808 OD/T808 Mod and Compressor 1 Modern/Classic VCA can now be explicitly
selected by a per-scene design. Omitted model choices preserve the model.
The next owner-approved test verified automatic Drive/Compressor insertion,
including 20/20 combined insertion/configuration actions on323 with original
settings and shunts preserved. See the same evidence document for bounds.
This is not complete FM9 effect parity: automatic EQ insertion is still
gated; PEQ Q/types remain unchanged. Hardware acceptance
is first-instance channel A, with other channels preserved, not a claim
of every model/channel or acoustic match.

## Implemented and tested offline

| Component | Boundary retained in the port |
|---|---|
| Connection/readback | Model/checksum filtering, addressed replies, complete bulk blocks, passive display reads; no model-selector query |
| Scalars | 75 individually mapped controls, finite/range checks, independent display verification and captured zero setters |
| Delay time | Independently verify bulk plus display Tempo NONE before writing milliseconds; failed dependency stops the time write |
| Legacy cab mixer | IRs 1-4, channels A-D, full-block comparison; levels, pan and normal/mute/solo are distinct from IR selection |
| Models | Separate readable/selectable rosters; matching model is a no-op, changes are bypassed and quiet-staged with other-channel checks |
| Writes | Explicit external-mute acknowledgement and target preset; changed firmware/preset aborts, no automatic store or reload |
| Restore | Only independently established bulk laws, exact word verification, no guessed alternate opcode |
| Batch | Validate all static values before the first write, stop after the first failed verification |
| Cab lists/selections | Atomic Factory/User name imports with explicit bank/slot bounds; independent IR1/IR2 selection, preserving other slots and mixer state |
| Grid | Empty-grid serial construction or exact existing-route reuse; no implicit overwrite, flattening, deletion, preset reload or flash store |
| Modifiers | Inspect all 32 slots, refuse unassessed active targets/curves; preserve existing curves on source reassignment. Captured native Wah creation is exposed only through explicit user controller choices, not arbitrary AI parameter bindings |
| Execution seam | Preflight the whole action list and route before construction; explicit model channel/final level, first-failure stop, partial-edit recovery warning |
| Transport cleanup | Release the input if opening the output fails on either backend; no FM9 invariant-guard change |

Unknown readings fail closed. A successful command receipt is not a
successful verification. None of these checks measures loudness, pedal
movement, sound quality or audio feedback, and none is a physical limiter.

Model selection resets a channel's voicing. The executor must choose the
channel/model before setting gain/EQ/effect parameters. IR slots 1 and 2 do
not mean stereo pan; a selected IR may still be muted or excluded by solo.

## Remaining integration gates

1. Controller browser-to-hardware and physical acceptance passed on
   2026-10-01 (see checkpoint below). Acoustic acceptance remains separate.
   Complete text-generated rigs still need independent hardware acceptance.
2. The bounded text workspace now connects planner reference, compilation and
   reviewed execution. Broader manual controls, arbitrary routing and recovery
   remain separate integration work.
   Do not expose FM9 reamp/capture or startup global-restore actions to AFX3.
3. Deliberately reconcile the owner's audio-reference and conversation UI
   with upstream's newer sound-check/tone-match and amp/cab metadata features.
   Preserve provider choice, no paid fallback, and measured-vs-heard labels.
4. Keep running focused/full offline regressions and UI/package checks on
   the application path, not just the independent adapter.
5. After the complete application path is verified offline, reconfirm external
   mute and use only authorized
   test slots 321-329. Compare with Axe-Edit and independently read all four
   scenes. Human listening and physical pedal tests remain necessary.

Hardware was intentionally off during the initial foundation work. Historical
[2026-09-19 acceptance](AFX3-PARITY-2026-09-19.md) documents the old code,
not a hardware pass for this port. A stored preset reload can discard all
unsaved work; permanent storage and global pedal changes require separate
explicit permission. Neither operation is enabled in this adapter.

### Next hardware checkpoint: read-only, not the integrated server

After the owner confirms power and external mute, stop TC and Axe-Edit so
only one process owns MIDI. From this integration worktree run:

```powershell
.\.venv\Scripts\python.exe -m tools.afx3_integration_readback --hardware-read-only
```

This tool refuses `TONECOMMAND_SIM=1` rather than labelling simulation as
hardware. It imports no server, enters no edit session, and does not change
the selected preset, scene, channel, global mapping or stored data. It reads
the current channels, passive models/parameters, cab mixer, grid and modifier
slots, with before/after preset, scene and block-status consistency checks.
Keep any raw user-preset/modifier reports private under ignored backups.

The physical pedal's connection point must be known before deciding whether
External 1 is the right source. Missing or structurally plausible curve words
are not permission to synthesize a transfer function. A separately reviewed
Axe-Edit comparison and physical sweep test are still needed. The broad
modifier/topology capabilities remain disabled: these narrow internal
operations do not implement every upstream editor operation.

## Verification record

The original fork baseline passed 2,691 tests with one skip in UTF-8 mode.
Unmodified upstream passed 2,459 with 21 skips and one environment failure:
this Windows account cannot create a symbolic link (WinError 1314). The test
now explicitly skips only that unavailable prerequisite, without weakening
the application's path containment check or swallowing other OS errors.

191 targeted adapter/profile/model/cab tests pass locally on Python 3.12.10.
These use independent scripted ports and test doubles, not FM9Sim posing as
an AFX3 and not an acoustic/hardware acceptance claim. Full integration
baseline and foundation JUnit reports are kept locally under
`backups/integration-20260929/`.

Final upstream-plus-foundation run: **2,650 passed, 22 skipped** in 263.38 s
with `TONECOMMAND_SIM=1`, `PYTHONUTF8=1`, Python 3.12.10 and six pytest
workers. Report: `adapter-foundation-final.xml`. The required device-handle,
capability-gates and UI-warning run separately passed **54 tests** in
123.23 s; the focused adapter, packaging and site suite passed **207 tests**.
The preceding full run exposed a bad generated documentation link; that was
corrected before the final all-green run. Skips include the unavailable
Windows symlink prerequisite and 21 existing upstream skips.

A wheel was built and the adapter plus both packaged JSON model inventories
loaded directly from that wheel under isolated Python (`-I`), without opening
MIDI. This checks the new package's resource inclusion, not a complete
installed-GUI or frozen-application acceptance test.

The repository's required device-handle/capability/UI-warning suite must
also pass before each commit. CI, another computer and the real device
remain unproven until their own runs exist. No push/PR is authorized yet.

### Cab, routing and modifier checkpoint (2026-09-29)

Final full run: **2,751 passed, 22 skipped** in 365.23 s with the same
Python 3.12.10, UTF-8/SIM environment and six workers. JUnit:
`routing-final.xml`. Required gates separately: **54 passed** in 128.52 s
(`routing-final-required-gates.xml`). Focused adapter, transport, packaging
and site suite: **318 passed** in 11.62 s (`routing-focused.xml`). Reports
remain private in `backups/integration-20260929/`.

The wheel build and isolated imports also pass, including all six new AFX3
modules, the read-only inspection tool and firmware-pinned JSON resources.
Wheel SHA-256: `7c5992e59765b99a0b7550dc7cd3cf5cf2c7d9599ceb767fe8983232bb3aa61e`.
The first no-build-isolation attempt lacked setuptools in the virtualenv;
the normal isolated build then succeeded. No application dependencies or
the working installation were replaced for this check.

No MIDI port was opened and no real-device result is claimed in this run.
The owner has been asked to power on the muted unit, release its MIDI port,
and identify the pedal connection for the next read-only checkpoint.

### First real-device read-only observations (2026-09-29)

The owner supplied an existing Wah preset on FW 32.06. Independent reads
confirmed Cry Babe, one External 1 binding targeting Wah Control, and a
complete 25-word modifier record. During 180 passive samples, Control read
0 while both bypass states were observed; the modifier record was equal
before and after. This is not an acoustic sweep or measured pedal range.
The report now explicitly labels modifier-controlled display values as
unverified effective values rather than treating zero as a dead pedal.

Axe-Edit was opened separately after releasing the observer's MIDI port.
Its Wah page independently showed Modifier Enabled and Cry Babe. The user
reports that its bypass/enable follows their pedal. A later UI observation
held a fixed display value; the two observations were not simultaneous and
must not be used as a calibration comparison. A separate 25-second USB
input-only listen received no CCs; this does not establish absence of CCs
on the controller's hardware-MIDI link.

The owner's separate controller source uses configurable CCs and hardware
serial MIDI. No controller-specific CC mapping is embedded in TC. That
other project was inspected but not modified or flashed. All captures,
raw curves, preset identities and source-review details remain private in
ignored backups. No preset/scene/channel, parameter, global setting or
store was written by this inspection. A working fresh-binding write and
its audible sweep remain unverified; an existing curve read is not a SET
encoding calibration or permission to write unknown fields.

Changed inspection/modifier tests: **18 passed**. Required device-handle,
capability and UI-warning checks: **54 passed** in 112.46 s. Report:
`pedal-readback-gates.xml`. The earlier complete-suite result above remains
the last full run; these changes have focused, not repeated full-suite,
coverage.

### Native modifier allocation checkpoint (2026-09-29)

The owner selected a disposable test preset and authorized muted hardware
testing. Two isolated Wah blocks were used, with no Input, Output or cables.
No store, preset reload, global MIDI setting or original-app code was changed.

Passive Axe-Edit captures on FW 32.06 showed a separate native allocation
command before the source SET. Merely opening an unbound modifier dialog
did not send this command. Selecting External 1/2 did:

```
Wah 1: f0 00 01 74 10 01 3a 00 5e 00 05 00 00 00 00 00 00 00 00 00 00 75 f7
Wah 2: f0 00 01 74 10 01 3a 00 5f 00 05 00 00 00 00 00 00 00 00 00 00 74 f7
```

Source selection then targets the allocated modifier slot, not the Wah block.
The device supplies the full 25-word curve. `create_wah_modifier` is limited
to these two captured targets. It refuses existing target records, requires
all slots readable, checks that exactly one unassigned slot acquired the
captured device defaults, then sends only the source selector. Other slots,
grid, scene and block status must remain unchanged. Allocation is sent once;
failed reads never cause a retry of the allocation or a guessed slot write.
The default record is comparison evidence, never a raw curve-write template.

After Axe-Edit released Wah 2's source, the new adapter recreated it with
External 2. Independent bulk readback matched all 25 words and every other
slot was unchanged. Axe-Edit, reopened as the only MIDI owner, independently
showed External 2, Modifier Enabled, Min 0 / Max 10, and Auto Engage Off.
This verifies a recreated binding in the edit buffer, not flash persistence,
an acoustic sweep, global CC mapping, or fully integrated planner behavior.
Auto Engage Off means this test does not promise automatic bypass at heel.

The owner has been asked to move the second physical pedal while viewing
the modifier indicator. Until physical acceptance and executor integration
are complete, the planner continues to reject a new binding before building
blocks. General modifier capabilities remain false; only the experimental
direct adapter method gained the captured allocation operation. Raw captures
and user-preset records stay in ignored local backups.

The changed native-allocation, adapter, existing-modifier and executor tests
plus mandatory device-handle/capability/UI-warning gates passed together:
**145 passed** in 229.86 s, UTF-8/SIM mode, Python 3.12.10. Report:
`native-modifier-gates.xml`. The previous full-suite run is still the last
full-suite result; this checkpoint did not rerun every unrelated test.

### Owner-supplied Wah and volume reference

Independent bulk reads paired with fresh Axe-Edit UI observations confirmed
Wah 2 Control on External 1 with Auto Engage Fast Pos, and Volume/Pan 1
Volume on External 2 with Auto Engage Off. The volume target is effect102,
parameter0: this is NOT its model selector. Modifier diagnostics now name
that observed target without creating a writable parameter specification.
Observed Auto Engage words 0/6 are labelled Off/Fast Pos for the verified
Wah targets; volume has only the observed Off label. No SET law is inferred
from those read values, no unknown mode names are guessed, and physical
bypass is not certified from a snapshot. A volume modifier still fails
write preflight pending captured, independently verified write support.

The user reference has parallel branches, intentionally left intact. The
read-only report explicitly states the existing serial validator's scope;
rejecting that topology does not prove it has a broken audio path.

A subsequent attempt to capture an Auto Engage change was interrupted before
any UI write because Windows had no usable interactive desktop. Mouse input
and later screenshot capture failed. Independent MIDI readback confirmed
all 32 modifier records unchanged. No guessed command was substituted for
the missing capture. Completing Auto Engage and volume creation still needs
an active editor session for the controlled comparison.

Verification: **165 passed** in 123.18 s, including the changed modifier,
readback, native-allocator, executor and adapter tests and all required
device-handle/capability/UI-warning gates. UTF-8/SIM mode, four workers;
report `modifier-observations-gates.xml`. A further real-device read-only
run confirmed the new observed labels on the owner reference. No new write
capability or complete-suite/installed-app acceptance is claimed.

### Bounded pedal execution checkpoint (2026-09-29)

A resumed interactive Axe-Edit session supplied independent captures for
Wah Auto Engage Fast Pos -> Off -> Fast Pos and Volume/Pan 1's native
modifier allocation. Independent MIDI reads followed each editor handoff.
The captured mode setter is typed command 01 09, modifier parameter 10,
ordinal 0 or 6. Zero here is a captured SET, not an inferred query or a
reason to permit zero writes to unrelated parameters. Volume allocation
is command 01 3A targeting effect 102, parameter 0. Source assignment
targets the allocated modifier slot, not the Volume block's parameter 0.

`bind_pedal_control` and a pedal-only `pedal_control.execute` seam now check
the complete request before execution. They accept only captured Wah 1/2
Control and Volume/Pan 1 Volume, explicit External 1/2, and optional Off or
Fast Pos for Wah. Volume requires Off, the exact observed full-range curve,
Type Volume and the captured 0 dB Level on all four channels. These are
comparison gates, not inferred scalar conversion laws. No curve, level,
global MIDI mapping, channel, scene or grid is written. An existing parallel
grid is compared unchanged; no serial flattening is attempted. The target
Wah's bypass may change as a legitimate consequence of Auto Engage.

Native allocation is never retried after a missing read. Exactly one free
slot must acquire the complete device-built record before source assignment;
all 32 records are independently checked after each write, including no-op
requests. Missing/changed state stops execution. Partial changes can remain
in the edit buffer; no automatic rollback or flash Store is provided.

Hardware replay by the new adapter successfully changed Wah 2 from Fast Pos
to Off and back to Fast Pos. Independent readback verified both operations;
all 32 records, Volume block words and the full grid matched the initial
reference afterwards. The two-pedal executor also passed as a verified
no-op on the restored reference. This is not a physical sweep/bypass test.

A further TC hardware round-trip reassigned the EXISTING Volume modifier
from External 2 to External 1 and back to External 2 under external mute.
Only that record's source word changed in the middle snapshot. Final
preset, scene, grid, status, all 32 records and Volume bulk matched exactly.
Auto Engage stayed Off and no Volume/Level scalar was written. This proves
source reassignment, not allocation of a new Volume modifier or live sweep.

Volume allocation and source selection were captured and independently
verified through Axe-Edit, but replay from TC remains pending. The attempt
to release its existing binding for that test failed at mouse input because
Windows again had no active interactive desktop. No binding was released:
subsequent readback verified the original External 2 record intact. The
user's Wah remains External 1 / Fast Pos. No arbitrary unbind command was
substituted. An active desktop is required to complete this hardware gate.

The application, device selector and general tone executor are NOT enabled
by this checkpoint. The Volume scalar/model registry and original FM9 paths
remain unchanged. Off Value writes, other Auto Engage modes, arbitrary
Volume curves/types/levels, global pedal setup and physical loudness are
not verified capabilities. Raw records and captures remain private.

Verification: complete SIM suite **2842 passed, 22 skipped** in 324.18 s,
Python 3.12.10, UTF-8, six workers, `pedal-control-full.xml`. This includes
the required device-handle/capability/UI-warning gates and the new exact
frame, allocation, refusal, collateral-change, settling and no-op tests.
Hardware evidence separately records the two successful round-trips above;
neither a passing suite nor readback proves acoustic pedal behavior.

### Native Volume allocation hardware acceptance (2026-09-29)

After the owner restored an active desktop, Axe-Edit released the existing
Volume/Pan 1 source to NONE under external audio mute. Independent readback
confirmed the target record was released before TC attempted allocation.
The new adapter then successfully called `bind_pedal_control(102, 13, "Off")`:
the device created its native modifier record and TC assigned External 2.
All 32 final modifier records, Volume block words, grid, block status,
preset and scene matched the original reference exactly. No Store occurred.

Axe-Edit was reopened as the only MIDI owner. Its freshly loaded modifier
UI independently confirmed Volume/Pan 1 Source 1 External 2 and Auto Engage
Off, full Min 0 / Max 10 range and Level 0 dB. Wah 2 remained External 1
with Fast Pos. Initial UI assertions ran before the dialog had fully loaded;
a settled read and screenshots confirmed the result, without another write.

This closes the native Volume allocation/recreation hardware gate above.
Physical pedal motion, heel bypass and audible level behavior still require
the owner's acceptance; no global CC mapping or sound-match claim is made.
The adapter remains an integration component, not a registered app feature.

Documentation checkpoint gates: **101 passed** in 116.14 s (SIM, UTF-8,
four workers), covering device-handle, capability, UI-warning and pedal
execution tests; `native-volume-hardware-gates.xml`. Implementation is
unchanged since the complete 2842-pass/22-skip suite above.

### User-selected controller workflow (2026-10-01)

The TC shelf now links to `/controllers`. Explicit connection selects the
AFX3 adapter and its own registry; loading the page itself never connects
to MIDI. Close Axe-Edit and other TC MIDI owners before connecting. The
workspace is intentionally separate from the unported general tone planner,
not a claim that the complete FM9 workflow already runs on AFX3. Disconnect
releases MIDI and returns to the normal TC context. Existing production TC
remains untouched in its separate worktree.

Only present, preflight-eligible Wah 1/2 and Volume/Pan 1 controls are offered.
Users choose External 1/2 explicitly; no controller CC is hardcoded. Existing
curves and ranges are preserved. A fresh binding uses the captured native
device initializer. Wah offers preserved mode, Off or Fast Pos; Volume is
restricted to Off. Unbinding, other sources, editable curves, amp/delay
modifiers and arbitrary Volume types/levels are not enabled. Unsupported
states are explained instead of silently replaced. There is no automatic
preference application or AI selection of the user's pedal source.

Read and review perform no SET. The server issues a single-use, five-minute
ticket bound to the adapter instance, exact request, preset/scene, routing,
block/channel state, all modifier records and relevant Volume bulk state.
Sending requires target confirmation and external mute acknowledgement,
fresh preflight, matching reviewed state and independent post-write readback.
Tickets are consumed before I/O; failures never auto-retry. Preset/connection
changes, GIG LOCK, active tone plans and cab auditions are refused. No Store,
global MIDI writes or automatic Undo is offered; partial writes may remain.

The controller page uses text-only rendering of device strings, disables
Send until both acknowledgements are checked, invalidates the displayed
review after a changed selection and shows readback failure distinctly.
Device selection and the shared writer lock are integrated with the host;
legacy API routes and `get_fm9()` refuse AFX3 outside this workspace. The
FM9 transport, global-restore code, protocol guard and whitelists are not
modified. Page assets use existing resource paths and packaging conventions.

Earlier physical acceptance: the owner confirmed Wah marker movement and
automatic bypass, and Volume marker movement on the recreated binding.
Volume staying active through the complete sweep was not separately
confirmed, and no audible level/sound-match acceptance is inferred.

Start this separate integration workspace on Windows with
`tools/start_controllers.ps1` (default port 8910). The script checks the
endpoint before reusing a listener, starts only on localhost, launches Chrome
if installed and never connects MIDI automatically. `-NoBrowser` and `-Port`
are available. The page can also be opened at `/controllers` on an already
running integration server. Disconnect here before reopening Axe-Edit.

Verification: complete offline suite **2869 passed, 22 skipped**, 464.25 s,
UTF-8/SIM with six workers, `controller-workspace-full.xml`. The final
cross-origin request guard and malformed-ticket validation were added
afterwards: controller/pedal tests **79 passed**; final mandatory and
controller UI gates **86 passed**, 202.50 s, `controller-ui-final-gates.xml`.
Real Chrome browser
tests exercised selection without writes, dirty-review invalidation, both
acknowledgements, one-shot send, failure messaging, failed-connection exit,
HTML injection protection and a 390-pixel layout using mocked API data.
They sent nothing to hardware. The PowerShell launcher passed parsing,
startup and reuse checks; the live local page reports disconnected.

### Live controller and physical acceptance (2026-10-01)

With external mute reconfirmed, the real Chrome interface on preset 324,
scene 1, FW 32.06 passed six reviewed sends: Wah 2 External 1 -> 2 -> 1;
Volume 1 External 2 -> 1 -> 2; Wah Fast Pos -> Off -> Fast Pos. Independent
readback verified every send. Separate before/after captures of all 32
modifier records, current block/channel/bypass state, complete grid and
all 12 present block bulk payloads were identical at the end. Out 1, routing
and global mappings were not edited; no Store or preset reload occurred.

Afterwards the owner explicitly confirmed the physical test: Wah follows
External 1 and bypasses at heel; Volume follows External 2 without automatic
bypass. This completes the bounded controller workflow, not tone matching,
calibrated loudness or general preset generation. Raw captures remain private.

### Upstream 1.5.4 integration (2026-10-01)

Merged the 19 upstream commits after c2c8a87. Both device-list entries survive
the merge: the new BOSS IR-2 and the explicit AFX3 controller workspace.
The upstream main-page missing-brace repair and Node syntax regression guard
are included, together with IR-2 named-parameter planning and deterministic
settling tests. Local AFX3 code and its verified controller page are unchanged;
general AFX3 planning, global restoration, reamp/capture and unverified
parameter writes remain blocked. Upstream named-parameter capability defaults
to false on this adapter; it does not grant new wire-format permissions.

The original production worktree is unchanged. This merge uses a separate
SIM server for browser checks, no hardware connection, writes or paid AI
calls. Public docs retain the distinction between upstream features and
completed Axe-Fx III integration. `tests/main_ui.browser.cjs` checks real
Chrome parsing, SIM polling, text input, settings/activity drawers and text
size, blocks all POSTs, and never requests an AI plan.

Verification: full SIM suite **2950 passed, 22 skipped**, 328.23 s,
`merge154-full.xml`, six workers, UTF-8. Subsequent packaging-list correction
and two extra regressions passed the mandatory/focused final gates:
**103 passed**, 114.87 s, `merge154-final-gates.xml`. Final documentation,
packaging, syntax and controller checks: **49 passed**. Real Chrome main
UI smoke and controller browser tests passed. The built 1.5.4 wheel was
installed into an isolated target and imported with Python `-I`: AFX3
registry/resources and controller module, IR-2 simulator and ToneX module
all loaded from that installation. This is package/module verification,
not a new hardware or frozen-application acceptance claim.

### Bounded text design workspace (2026-10-01)

`/axefx3`, linked from the main shelf and controller workspace, now connects
the selected AI to the AFX3 reference/compiler/review/executor path. It does
not route an Axe-Fx III through the FM9 executor. Connect explicitly in
`/controllers`; no page opens MIDI automatically.

The initial scope is text, 1-4 scenes, one amp model with independent voicing
on A-D, one shared Cab channel, optional Wah, Delay and Reverb. Only a verified
empty grid or an exact compatible serial route can be used. Existing
parallel routes, extra effects or missing blocks on an existing route are
refused without erasing or reloading that preset. In particular, reference
preset 324's parallel controller test must not be flattened by this builder.

The AI returns a strict musical design, not raw actions. TC compiles channel
selection, model-before-voicing order, explicit final effect levels, IR mixer
normal/mute/pan/level state and scene names. Each amp/delay/reverb scene uses
its own channel; shared Cab/Wah and other scenes can still be affected.
Controller source is the user's separate External 1/2 choice, not a guessed
CC. The native Wah binding runs after model/voicing actions and verifies all
modifier records; the existing controller workspace remains available for
Volume. No new arbitrary controller parameter/range writes are exposed.

Factory/User name imports are device-specific and connection-scoped. They
upload names, not IR audio, and must correspond to the unit's actual slots.
The planner cannot pick an address outside that imported catalogue. Amp
facts are matched to the AFX3 roster by exact unique name, never FM9 ordinal.
This is not automatic discovery or a claim that catalogue names prove IR
contents or tonal resemblance.

The user must choose one AI backend explicitly. The owner's direct Codex
CLI choice is restored with UTF-8 input/output, optional model override,
temporary final-message capture and no automatic provider fallback. CLI
read-only/ephemeral flags are not a physical audio safety boundary. Other
configured TC backends remain selectable. For OpenAI-compatible requests,
the top-level system instruction now honors the device-specific instruction
instead of always inserting the FM9 one. No real AI account was called by
the automated tests.

A review binds the device connection, preset/scene, complete grid, present
block bulk reads, all 32 full modifier records, scene names and cab catalogue.
System status records 200/201 are retained in the fingerprint but are not
queried as parameter blocks. Reviews expire after ten minutes, are single-use
and are invalidated by changed state. Both target and external-mute consent
are required again before send. A verification failure stops execution;
partial edits may remain, with no automatic Undo, Store or preset reload.

This is an experimental source-worktree integration. Full text-preset
hardware/physical/audio acceptance remains pending. Audio/web links,
isolated-guitar extraction, measured tone matching, the old design
conversation and broader manual controls are not yet integrated into this
new workspace. Do not describe the controller checkpoint or mocked text
tests as acceptance of those features or of arbitrary Fractal parameters.

Verification: full SIM suite **2991 passed, 22 skipped**, 280.43 s,
`text-workspace-full-final.xml`. Mandatory/focused gates **332 passed,
1 skipped**, 238.34 s, plus subsequent text/native-pedal checks **76 passed**.
Real headless Chrome passed the local-asset/mocked-API test covering Enter
newline, explicit send, both consents, changed drafts, failed AI/readback,
XSS-safe rendering and mobile layout. The test initially caught missing Wah
option tags; fixed and rerun. The first full suite caught the stale measured
server line count; fixed before the passing rerun. Source imports and the
wheel module list were checked; no frozen/distributed GUI acceptance claimed.
After persisting the owner's Codex choice locally, the global test fixture
also isolates the AI settings file so tests cannot use that real account.
The final mandatory/text/settings gates passed **218 tests, 1 skipped**,
114.79 s, `text-final-isolation-gates.xml`. Runtime starts disconnected on
loopback port 8910; no new hardware writes or actual AI calls were performed.

### First full text build hardware readback (2026-10-01)

The owner authorized disposable preset 322 and confirmed external audio mute.
The original server released MIDI before the integration server connected;
only one MIDI owner was active. Preset 324 was not selected or modified.

Initial real Codex requests timed out because the imported upstream CLI
environment omitted Windows runtime paths. A bounded subprocess DNS test
reproduced error 11003 with that environment and succeeded with SystemRoot
and the original profile paths restored. The same selected Codex CLI then
answered a small diagnostic in 5.7 seconds and produced the full text design.
No model, reasoning setting, login, DNS configuration or provider was changed.
The temporary timeout override was removed. Unit tests preserve credential
isolation while covering Windows runtime paths for all three CLI backends.

The owner's cab text file contains larger User banks than this importer's
verified address mapping. Only nonempty User 1 slots 1-512 were imported for
this acceptance pass. Do not infer that User 2/3 or the entire file is
supported, and do not remap the remaining slots without protocol evidence.

The real `/api/axefx3/plan` and single-use `/send` path built an initially empty
preset, named AI-Whole Lotta Love: Input 1 -> Wah 1 -> Amp 1 -> Cab 1 ->
Delay 1 -> Reverb 1 -> Output 1. All **163 actions succeeded**, none skipped.
After disconnecting the server, a separate MIDI session visited scenes 1-4
and passed **193 independent comparisons** against the reviewed plan.
These were new device reads, not copies of the send acknowledgements.

| Scene | Amp channel | Input drive | Delay | Amp level |
| --- | --- | --- | --- | --- |
| Intro Wah | A | 5.8 | 115 ms, 14% feedback, 10% mix | -16.5 dB |
| Main Riff | B | 6.7 | Bypassed | -16 dB |
| Heavy Riff | C | 8.3 | Bypassed | -17 dB |
| Lead Wah | D | 8.8 | 285 ms, 23% feedback, 16% mix | -14.5 dB |

All four amp channels independently retained Plexi 50W High 1 and their own
EQ/master values after scene changes. Cab A IR1 uses wire bank 2/ordinal 27
(imported User 1 slot 28, Brit Black GB25 57+421 MPT), normal/in mix, 0 dB,
center; IR2-4 remain muted. Delay/reverb use independent A-D channels with
final block levels 0 dB; Output 1 A reads -6 dB. Wah A reads Cry Babe and
0 dB, with one full-range native External 1 modifier and Fast Pos Auto Engage.
The audit deliberately does not assert static Wah bypass: Auto Engage can
follow the physical pedal, including on scenes intended to bypass it.
Scene-specific Wah behavior requires the physical acceptance test.

The device was left on scene 4 of the unsaved edit buffer. No Store, preset
reload, global MIDI mapping, unrelated preset edit or automatic rollback was
performed. Raw captures and plan/result files remain private. This verifies
the bounded text-to-hardware path, not acoustic gain, physical pedal sweep,
equal scene loudness, bypass transparency, a recording match or audio/web
analysis. Those acceptance steps remain outstanding; no audio was supplied
or heard during this build.

Software verification for the Windows fix: planner/backend tests **46 passed**;
mandatory device-handle/capability/UI-warning gates plus both planner suites
**100 passed**, 212.04 seconds, in SIM mode. The earlier full-suite result
above is historical, not a new full-suite run for this patch.

### Autonomous offline follow-up: explicit Wah mode and readable review

The text workspace now exposes the already captured Wah Auto Engage modes
Off/Fast Pos and a preserve option. The choice is passed independently of
the AI design, validated by the request schema/compiler, included in review
metadata and sent only through the existing reviewed native binding. An
omitted API field retains the previous Fast Pos behavior for compatibility.
Without a selected controller, no binding or Auto Engage action is added.
Preserve does not invent a mode: existing records are retained; a newly
allocated modifier keeps the device's native default.

Fast Pos has an explicit warning: all planned scenes share Wah A, and pedal
movement may change bypass even in a scene designed with Wah off. Off leaves
engagement to scene bypass while the pedal continues to control filter sweep.
This is not new evidence about the physical behavior of preset 322. That
preset and its current Fast Pos setting are not changed by this UI work.

Review shows planned amp channel/gain/level, Wah, delay time/feedback/mix and
reverb per scene. Cab names and display positions come from the imported
catalogue, alongside internal addresses in the API metadata; the AI does not
invent these labels. The request collapses only after a successful proposal
and reopens with the original text intact. Changing mode/source/request
invalidates the displayed review and both confirmations. New review text
uses textContent, including imported names and warnings.

No new MIDI operations, global mapping, Store permission, bank remapping,
audio upload or web fetching is enabled. Larger User export banks remain
blocked instead of being silently truncated/remapped. Acoustic and physical
pedal acceptance remain separate from automated software tests.

Verification: focused planning/pedal tests **85 passed**; mandatory and
focused gates **139 passed**, 109.02 s; final full SIM suite **3004 passed,
22 skipped**, 281.47 s (`wah-choice-full.xml`, eight workers). Real headless
Chrome with local assets and mocked APIs passed mode selection, request
retention, review invalidation, consent, safe text rendering, table and mobile
layout checks. The test's former visible-button wait was corrected for the
new collapsed request. Private desktop/mobile screenshots were inspected.
The local live server was restarted via normal disconnect and SIGTERM,
then reconnected with the same 512-name catalogue. Read-only before/after
state confirms preset 322, scene 4, names and serial route unchanged. No
hardware send or real AI request was made during this follow-up.

### Delay-ready new presets (2026-10-06)

New empty text builds always allocate Delay 1 after Cab, even if the design
requests no audible delay. TC explicitly voices its channel and final level,
then leaves it bypassed in dry scenes. A later request can enable that block
through the existing reviewed executor, without moving blocks or rebuilding.
This does not enable arbitrary insertion or destructive reconstruction of an
existing preset. Such routes still require separately verified placement.

The bounded ambience builder rejects an active delay before Cab instead of
silently sending a tone through an unsuitable route. An inactive delay can
retain its existing location; no move, clear or cable replacement is enabled.
Stereo delay selection, Spread and L/R Ratio are still unported. The presence
of a mono delay is not evidence of adjustable stereo width or exact recording
timing. Independent readback and physical listening remain separate checks.

Verification for this change: mandatory device/capability/UI gates plus text
planning, grid and executor tests passed **120 tests**, 112.79 seconds in SIM.
The real headless Chrome local-asset/mocked-API browser test also passed. No
new preset construction or audible delay acceptance was performed for this
change; the running TC was restarted disconnected without reloading the unit.
