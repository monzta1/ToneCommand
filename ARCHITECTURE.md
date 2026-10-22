# Architecture

What this program is shaped like, why, and what is wrong with it. Written
2026-09-01 against 871 tests passing.

## The one-sentence version

A local FastAPI server owns the only connection to the FM9 and exposes it over
HTTP; a single-page browser UI drives it; an LLM turns sentences into proposed
parameter changes that a human confirms before anything is transmitted.

## The shape

```
  browser (ui/)                    server.py                  fm9/
  ────────────                     ─────────                  ────
  conversation ──── /api/chat ──── planner.converse ────┐
  prompt ────────── /api/plan ──── planner.plan ────────┤ backends:
  confirm gate ──── /api/apply ─── run_action ──┐       │ openai / cli
  sliders ───────── /api/apply ─────────────────┤       │ grok / api
  scenes, chain ─── /api/state ─── snapshot ────┤
                                                 ↓
                                          device.FM9 ──── MIDI SysEx
                                          sim.FM9Sim ──── in-process fake
```

Everything that reaches hardware goes through `run_action`, and nothing
reaches `run_action` without a human pressing TRANSMIT. That is the single
invariant this codebase is organised around.

## Layers, in dependency order

Experimental AFX3 work is isolated in `devices/axefx3`; the `/controllers`
workspace explicitly connects its own device context for reviewed Wah/Volume
bindings. `/axefx3` adds bounded text designs compiled by `planning.py`, with
state-bound review/send in `tone_ui.py` and `tone_review.py`. Generic API routes and the FM9 handle are refused while this
context is selected. It implements the adapter contract without FM9
transport inheritance or FM9 global routing restore. Its own firmware-pinned
registry and captured SET domains prevent a product-byte-only substitution.
The isolated executor validates the whole plan before routing construction,
preserves separate scene/channel intent, and stops at the first failed
readback. Cab imports/selections and narrow grid/modifier operations remain
behind this boundary; broad topology/modifier capabilities stay disabled.
See `docs/AFX3-INTEGRATION.md` for the remaining
server/UI and hardware gates. `server.py` has 8,481 lines in this stage.

FX3 reference measurements and descriptive comparison live in the side-effect
free `audio_measurements.py`; their endpoint does not obtain a device or call
an AI. Sanitized numeric evidence can accompany private design-history v2,
never executable actions or old approval. `effect_controls_fw33.py` holds
captured Compressor/GEQ facts separately from typed voicing schemas and the
bounded reviewed-effect grammar. Disabled release flags remain authoritative
until normal SEND and independent editor acceptance, not simulator success.
FX3 `navigation` is an explicit human-only selection service, separate from
planner actions and automatic reload. State-bound single-use confirmations
protect scene/preset transitions; native readback verifies selection, not sound.
`block_probe.py` is a developer-only322 boundary for captured isolated blocks
and a fixed complete serial chain. Ordered one-use permits check fresh whole
grid states, including a separately bounded connection-only continuation.
It is not reachable from planner/API/SEND and does not authorize arbitrary
graph or model writes. Physical mute and measured output staging remain separate.
`serial_build.py` separately exposes only the independently measured14-cell
row1 template through normal reviewed execution. It never exposes a raw graph
encoder or developer probe. `serial_planning.py` compiles one-scene/A numeric
Amp/Delay/Chorus designs, retaining models/cabs and bypassing all reserves.
NAM-independent snapshots bind review to complete preset state. Single-use
sequence/bypass permits still require ordinary confirmed edit-session checks.
Source ingestion in `rig_source.py` reuses upstream `describe` and `riggraph`
with the explicitly selected text AI, not the FM9 executor or implicit Claude.
Sound references stay separate from rig explanations. The bounded FX3
translation exposes source provenance, topology/gear omissions and planned
effect activation; it does not promote firmware capabilities or prove sound.
The shared extractor's optional reader seam leaves the restricted image path
and default FM9 source behavior unchanged.
`tools/axe_edit_dialogs.py` is an optional Windows developer comparison helper,
not a server service or NAM installation dependency. It attaches only to an
already running measured editor executable and acknowledges only the complete
known Manage NAM information dialog. Unknown or changed dialogs stop before
comparison; screenshots/status stay in ignored backups. No MIDI owner, hotkey,
Save, overwrite or selector write is introduced by this helper.
FW33 numeric/NAM behavior is pinned in `fw33_profile.py`, guarded by `fw33.py`
and compiled through `nam_planning.py`. Native memory conversion/readback and
the two-phase installer stay inside the FX3 package. `nam_ui.py` registers
namespaced account/installation APIs and a separately confirmed same-slot
Store. The existing OAuth callback dispatches using the browser-bound FX3
cookie/pending state without replacing FM9's own OAuth path. No generic FM9
capture/reamp contract or never-brick guard is widened. See
`docs/FW33-COMPATIBILITY.md` for exact bounds and pending hardware acceptance.
`nam_selector.py` reads four-channel capture ordinals and performs the separate
scoped edit-buffer selection, not memory installation. Reviews fingerprint the
chosen full capture and all referenced channel captures. The AI cannot install
or override the user's slot choice: `nam_slot` is an explicit request field and
`select_nam` is compiled deterministically. Selection001-256 uses captured
ordinal units, separately measured zero, and independent bulk/memory readback.
Unreadable memory or stale review stops before transmission; no implicit
rollback, global mapping or preset reload is added.
`route_options.py` provides a read-only typed comparison of AMP/CAB with pedals
and NAM with effects, using the selected provider and optional local audio
measurements. Catalog research is metadata only; it selects/installs nothing.
The feature-negotiated GUI requires an explicit executable route choice and
shows unsupported approaches as musical alternatives, not available writes.
This does not enable FW33 amp model/CAB/routing/controller parity. Audio
measurements are reused for the same source within the request session, never
for a different URL/file. The installer adapts only a capture's display label
to the measured27-character ASCII header and shows the original catalog name;
capture weights, architecture and strict compiler validation are unchanged.
Controller routes live in `controller_ui.py`; `controller_review.py` binds
single-use, five-minute send tickets to a complete live state fingerprint.
Read/choose/review do not write. The shared writer lock, GIG LOCK, explicit
mute acknowledgement and device-side independent readback guard execution.

Interface languages are local data, not AI or device actions. `fm9/language.py`
serves a fixed asset allowlist. The bundled i18next engine translates registered
initial markup and explicitly marked messages; user input, live device readings
and existing plans are not scanned. English is the source and fallback. Imported
JSON is matched to its catalog hash, rendered as text, stored only in the browser
and cannot alter option values or critical English confirmations. Catalog and
release ZIP checks live in `tools/language_packs.py`.

| Layer | Files | Knows about |
|---|---|---|
| Protocol | `protocol.py` | SysEx bytes, effect ids, nothing above |
| Transport | `device.py`, `sim.py` | protocol, MIDI ports |
| Model | `registry.py`, `signal_path.py`, `editbuffer.py` | protocol |
| Reasoning | `planner.py`, `describe.py` | nothing device-specific except the reference text it is handed |
| Policy | `server.py` | all of the above |
| Presentation | `ui/index.html` | HTTP only |

The direction holds. `protocol.py` has no idea a planner exists, and
`planner.py` has no idea what a SysEx byte is. That separation is why the
simulator can stand in for hardware without either side knowing.

## What is actually wrong

Ranked by what it costs, not by how ugly it looks.

### 1. `ui/index.html` is 249 KB in one file

5,306 lines: 160 KB of JavaScript and 68 KB of CSS inline in one document,
with 109 top-level functions in a single flat scope.

The cost is not aesthetic. Three bugs in the last day were of a class a file
boundary would have prevented or made obvious:

- Handlers bound to `#knobs` while the graphic EQ lived in `#geqbox`, so the
  faders were dead on arrival and 501 tests passed over it.
- The same id (`cclear`) written twice in one template.
- A `[hidden]` attribute silently beaten by three different `display: flex`
  rules written hundreds of lines apart.

Everything is in reach of everything, so nothing can be reasoned about
locally, and the only way to catch a layout regression is a screenshot.

**Fix:** split into `ui/index.html`, `ui/app.css`, and JavaScript modules by
concern. Served as static files. No behaviour change, mechanical, testable.

### 2. `server.py` is 8,587 lines; routes include the bounded FX3 workspace, upstream discovery and local language assets

Every concern in one module: device polling, planning, applying, settings,
recipes, sharing, snapshots, profiles, slot admin. Eight pieces of
module-level mutable state and two locks whose interaction is not written
down anywhere.

The state is the real risk, not the line count:

```
_lock              the device.  Held across MIDI round trips.
_settings_lock     planner settings. Held across a whole LLM call.
_last_snapshot     last good device reading, for offline
_snaps             undo / A / B
_profile           a loaded foreign rig profile, which OUTRANKS the device
_gig_mode          refuses everything but scene changes
_preset_cache      slot names
_shared_cache      shared recipe map
_synthetic_slots   simulated empty slots
```

`_profile` outranking the live device is correct and surprising, and it is
enforced by an `if` at the top of two handlers. Nothing stops a third handler
being written without it.

**Fix:** split routes into modules by concern; move the mutable state behind
a small number of explicit accessors so the precedence rules live in one place
rather than in each handler's first three lines.

### 3. Two lock scopes with no written contract

`_settings_lock` is held for the duration of an LLM call, which can be four
minutes on a describe-build. Anything else wanting to save settings waits, and
`/api/ai-settings` returns 409 after 2 seconds rather than blocking. That is
the right behaviour and it is discoverable only by reading three call sites.

**Fix:** one paragraph at the top of the module saying what each lock covers
and what is legal inside it.

### 4. UNDO does not survive a restart

`_snaps` is a module-level dict. Restart the server and every undo, A and B
snapshot goes with it, while the edit buffer on the rig keeps the changes they
were the way back from. Found the hard way: a transmit, then a restart, then
an undo that answered "nothing captured in undo" with the changes still on the
hardware.

It is recoverable, because nothing is ever stored without an explicit SAVE, so
reselecting the preset discards the buffer. But "reload your preset" is a
worse answer than UNDO, and the button implies a promise the process lifetime
does not keep.

**Fix:** write the undo snapshot to disk beside the settings. It is a few
dozen parameter values.

### 5. Presentation logic in `server.py`

`slot_label`, `state_text`, and the plan-shape prose exist to be read by
either a model or a person. They are formatting, sitting in the policy layer.
Harmless today, and the first thing to go wrong when a second client appears.

### 6. `ai_settings.py` has grown a second job

1,024 lines. It manages planner settings, and it also now installs software,
edits a third-party YAML config, derives a password and runs `brew`. Those are
setup concerns wearing a settings module's name.

**Fix:** `fm9/setup_guide.py`, leaving `ai_settings.py` to settings.

## What is right, and should not be "fixed"

- **One writer.** The server owns the MIDI port. Every write is serialised
  behind `_lock`. This is why two browser tabs cannot corrupt a preset.
- **The simulator is a real implementation**, not a mock. It is why 871 tests
  run in under a minute with no hardware.
- **The failure taxonomy in `planner.py`.** Transport failure falls through to
  the next backend; a reply that parses but says nothing useful does not. That
  distinction is load-bearing and easy to get wrong.
- **`validate_action` is a chokepoint.** Every path that can produce an action
  goes through it, including the ones added most recently. There are tests
  asserting new entry points cannot bypass it.
- **Tests describe failures, not functions.** They are named after what went
  wrong and the docstring says what it cost. That is why they survive
  refactors that rename things.

## Invariants

Break these and the program is a different, worse program.

1. Nothing reaches hardware without an explicit human confirmation.
2. Firmware and bootloader messages are unreachable by construction, not by
   check. Rule zero: never brick a device.
3. Storing is whitelisted to configured slots and refuses everything else.
4. Every action is validated against the device reference before it is shown,
   whatever produced it.
5. An undo snapshot is taken before any write, automatically.
6. Pedal 1 is never touched.
