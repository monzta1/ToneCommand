# Opt-in Axe-Fx III reviewed Amp edit

Full-fork candidate,28October: default connections use `readonly_adapter`;
the opt-in writer uses that same read-only boundary plus its exact reviewed
operation. No writer/profile promotion follows from this namespace mapping.
New Design waits while a reviewed operation is in flight. The new script is
included in launcher source identity; added labels use bundled EN/NL/DE.
Browser POST origins must be actual loopback origins, not a reflected Host.

This is a small developer experiment, not full preset planning or a new
release. It builds on the separate single-edit bridge in #289. Normal
Axe-Fx III connections remain read-only and the FM9 flow stays unchanged.
No alternative GUI, installer, account workflow or firmware promotion is
included. Use official releases for ordinary use.

## Connection and supported operation

Only an explicit process environment setting,
`TONECOMMAND_AXEFX3_REVIEWED_AMP=1`, selects the existing `AmpWriter` when
connecting declared Mark II hardware. There is one connection and no
fallback to another writer. Mark I and Turbo experiments are refused;
their ordinary read-only connections are unchanged. Simulator mode never
opens physical MIDI through this factory.

The underlying writer keeps its exact measured firmware-response hash,
`045dd3498d485ee32ebf5e87540830429fddac821fee5851e109f4db3c056217`.
The label "FW33" alone is not permission to write. In particular the
current Beta 5 identity is **not** promoted by this contribution. It can
connect/read but the experimental form explains why editing is unavailable.

The only exposed edit is existing Amp 1/channel A Gain or Mid: one action,
finite values 0.1-8.0 in 0.1 steps, at most one displayed unit of change per
review. Preparing reads the full existing writer baseline, including all
four amp channels and all modifier records, and refuses unsupported state.
This does not configure models, routing, bypass, channels, levels, names,
controllers, NAM, cab slots or global settings. It cannot build or save a
preset and cannot turn an AI proposal into device writes.

## Existing screens, explicit player SEND

1. Stop Axe-Edit before connecting TC. Keep external audio muted. TC cannot
   measure or enforce physical loudness.
2. In Device settings, the opt-in form displays independently read Gain/Mid
   values. Choose the parameter and proposed value, then **Prepare reviewed
   edit**. The form is absent when this experiment is not enabled.
3. The existing PLAN and REVIEW screens show the one edit. Inline card
   editors are disabled; change the source form and prepare a fresh proposal
   rather than silently mutating a reviewed action.
4. CONFIRM identifies the Axe-Fx III, current preset/scene, edit-buffer-only
   destination and lack of automatic Undo. Other scenes sharing amp channel A
   may change. Confirm both the target and externally muted audio.
5. **ARM SEND** arms for eight seconds. It does not write. Only a deliberate
   **SEND TO AXE-FX III** click submits the edit. The native review expires
   after sixty seconds, including time spent reading and reviewing.
6. SEND reports independently verified success, a verified no-op, or a
   stopped/uncertain outcome. No automatic retry, rollback, Store or Undo is
   offered. Keep audio muted after an unconfirmed transmission and inspect
   the device before making a new decision.

Going back creates a fresh proposal and clears both confirmations. Discard,
new proposals, changes to action/target/connection, Gig Lock, expiry and
repeated SEND cannot reuse approval. Late HTTP responses cannot restore
invalidated client authority. Server-side checks remain authoritative even
if the page is stale or requests are submitted outside the UI.
No automatic shared-scene sweep runs for this proposal. The shared-channel
warning remains conservative; the page does not claim automatic Undo or a
passed musical tone check for a single parameter edit.

## Registered endpoints

- `GET /axefx3-reviewed-edit.js`: local static controller.
- `GET /api/axefx3/edit/state`: opt-in availability and independent displays,
  never SET. Unavailable hardware/firmware remains visibly blocked.
- `POST /api/axefx3/edit/prepare`: strict one-action proposal, explicit current
  wire preset and one-based scene, no whole-rig batch.
- `POST /api/axefx3/edit/review`, `/confirm`, `/send`: exact canonical actions,
  digest, opaque one-use token, pinned preset/scene and ordered phase.
  Confirm and send additionally require exact boolean target/mute consent.
- `POST /api/axefx3/edit/discard`: invalidation only.

All seven endpoints are in the capability test request matrix. New writes
do not enter the generic FM9 executor or widen shared capabilities. They use
the same host device-switch/Gig Lock lock and current writer object.
Cross-origin mutation is refused. A post-write readback failure produces an
uncertain, non-retryable result, not a claim that nothing happened.

The existing **Report a problem** remains available. The script-free
`/report` page includes the selected III context and works even when the
main page fails; GET and POST report generation do not query the device.
New fixed UI messages enter the shipped English catalog with the existing
Dutch/German fallback mechanism. Live device values and user text are not
translated.

## Acceptance scope

Registered-route tests use the real bridge and AmpWriter with independent
fake port responses, not the FM9 simulator. They cover ordering, replay,
strict validation, identity/target/connection changes, mute consent, native
uncertainty and no retry/Undo. Shipped-controller Node tests cover stale
responses, queued discard, dirty inputs, target changes, expiry and the
explicit SEND boundary. Actual Chrome was also driven through the existing
screens against the registered server with isolated fake ports/providers.

Native Beta 5 checks on a disposable Mark II preset used an additional
GET-only final-output boundary: availability and preparation refused the
unmeasured identity, zero SET frames reached the unit, and the read status
was unchanged. This is refusal acceptance, **not** a successful native SEND
on Beta 5. No preset was stored. Positive hardware acceptance of this final
UI integration on an independently measured writer profile remains required
before normal activation. Screenshots, raw captures and account data are
kept private; they are not shipped in this contribution.
