# Prepared Axe-Fx III review/confirm/send bridge

Full-fork integration candidate,28October: imports map to this fork's explicit
read-only namespace. The separate opt-in host layer is now registered in the
shared interface, with default read-only behavior and the unchanged measured
MK2 identity pin. The preparation-only statements below describe the bridge
component, not absence of the separate host wiring. Beta5 remains refused.
Final candidate software/native acceptance is recorded in the A-Z ledger.

This document describes the bridge-only review boundary in #289. The
separate opt-in host wiring is documented in [the reviewed-edit UI guide](AXEFX3-REVIEWED-EDIT-UI.md).
Its limited activation does not promote other operations or firmware.

This is **offline preparation, not a release of ordinary app writing**.
`server.py`, the main UI, AI planner, registry, capabilities, output guards
and existing writers are unchanged. No production route constructs or calls
`EditWorkflow`. Nothing here opens MIDI or adds a second GUI or installer.

## Prepared contract

The host explicitly injects **one** existing `NameWriter` **or** `AmpWriter`
on its current connection, its shared device-switch lock, Gig Lock state and
the existing `server.plan_digest` function. The bridge accepts exactly one
raw app-shaped action:

- `rename_preset`, exact printable name with no automatic prefix;
- `rename_scene`, explicit one-based scene to name, without selecting it;
- Amp 1/channel A `DISTORT_DRIVE` or `DISTORT_MID`, within the existing
  writer's finite bounds, decimal steps and maximum change per review.

Mixed batches, Store, builds, models, channels, routing, controllers, levels,
other parameters, instances or firmware/chassis do not gain permission.
The writer is never chosen by fallback or opened by this module. A normal
read-only adapter is refused. This is trusted developer composition, not a
sandbox for arbitrary Python code or a global write-capability declaration.

`prepare` validates raw fields before a shared Pydantic Action could coerce
a boolean to a number. It pins current preset/scene and keeps the opaque,
connection-owned native review server-side. The result has the existing app
action fields, `plan_digest` and `expected_preset`, plus an opaque workflow
token, explicit `expected_scene` and stage. This is a prepared response
contract, not newly registered HTTP endpoints.

The permitted sequence is `prepare -> review -> confirm -> send`. Confirm
requires exact `True` for target acknowledgement and externally muted audio;
SEND requires those flags again. Its request must arrive within an eight
second arm window and the underlying native review deadline. Once accepted,
the existing writer performs its full preflight and independently rechecks
its own deadline immediately before its one SET. The eight-second window
is for accepting SEND, not cancellation of an already accepted operation.

Each transition consumes its prior stage before validating. New/invalid
plans, discard, changed action or rationale, digest, token, connection,
preset/scene, Gig Lock, expiry and repeated/concurrent SEND cannot reuse a
confirmation. The full canonical action is compared in addition to the app
digest; a matching truncated digest alone is never authorization.

Only SEND delegates to the existing writer. Native uncertainty exceptions
propagate unchanged, with no retry, rollback, reload, Store or automatic undo.
A verified no-op reports `sent=False`. Output uses the ordinary results-card
shape but explicitly says `undo_available=False` and `stored=False`.

## Required work before activation

1. The underlying writer contributions, including the unused-modifier finding
   in #287, and the separate factual catalog #288 are now merged upstream.
   This bridge includes current main `4d81851` (v1.6.2 plus both follow-ups).
   That review does not make this bridge hardware-accepted or promote Beta 5.
2. Choose an explicit experimental host connection/opt-in policy. Do not
   construct two MIDI owners or flip general `can_rename`/`verifies_writes`
   merely to bypass the existing capability gate.
3. Dispatch the bounded contract before the generic FM9 executor, snapshots,
   batching and callbacks. Use the existing host device-switch/Gig Lock/
   reconnect lock. It is currently a non-reentrant `threading.Lock`: call
   bridge methods outside already-locked generic handlers to avoid deadlock.
   Do not unwrap gated devices into a general-purpose write fallback.
4. Add reviewed request validation and refusal handling before SSE headers,
   including the token, expected scene, target/mute flags and uncertain-send
   outcome. Add every production route to the capability request matrix.
5. Wire the existing REVIEW/CONFIRM/SEND controls, not another UI. The
   current FM9 confirmation promises UNDO and uses FM9 labels; neither may
   be carried into this bounded III path. Bind target changes, revisions,
   discard and reconnect to disarming. Add translations when UI text lands.
6. Run actual browser/registered-route tests, independent native/readback
   and Axe-Edit acceptance of that **final integration** before activation.

Current evidence is offline: independent fake ports with the real extracted
writers, strict phase/target/mute/revision/replay/concurrency tests, and a
hermetic TestClient sequence. The test-only HTTP routes are not the normal
server and do not prove the production UI or physical device pipeline works.
Historical writer acceptance is not acceptance of this new host bridge.

## Review boundary agreed with upstream

The bridge and production route/UI wiring are separate drafts, as requested
in the roadmap discussion. This draft is the bridge only. Its programmatic
`send` method is a host boundary, not an automatic-send product feature.
The later UI contribution must require the player's explicit SEND click,
reuse the existing stages and language packs, cover new routes in capability
tests, and retain Report a problem for the III even if the main page fails.
Only one owner may hold MIDI. No alternative GUI, installer, release build,
logo change or ordinary application write capability is part of this draft.
