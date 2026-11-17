# Existing-preset request and review workflow

This draft composes the focused observation, original-scene and scalar ports
with the original TC interface. The larger local integration is not imported.
It uses the existing planner interfaces and backends already on main. No
new provider, suspended backend choice or CLI runner is a dependency.
The ordinary III connection remains read-only. Enable only one explicit mode:
`TONECOMMAND_AXEFX3_EXISTING_SCALAR=1` selects the new existing-preset component.
Combining it with an older experimental Amp flag refuses connection before
opening ports. Declared MK2 and the exact measured official33.01 identity are
required; physical MK1 and other firmware acceptance remain separate.

The initial scope is not a full new rig builder or all Fractal controls. It is
existing Amp1/A Bassguy model0 and B VibratoLux model121, Gain/Mid, preserving
all other existing state. No route/model/cabinet/controller/level/Store action
is exposed. Do not present this bounded port as the full fork's functionality.

1. In the original Request screen, confirm the selected target and external
   audio mute. Read all eight actual scenes. This explicitly recalls scenes,
   returns the original one and writes no parameters.
2. Describe the adjustment in the usual request box. SEND REQUEST uses one
   explicitly selected provider, with no automatic or paid fallback. Shared
   FM9 musical rules are reference advice; exact scope/preservation wins over
   new-build recipes. Raw factory/system/modifier words never reach the provider.
3. If the goal cannot be met within the exact controls, TC asks one scope
   question in the conversation. The input is empty for the user's answer;
   the original request and bounded server-owned clarification history remain.
   An invalid design has at most one same-provider correction. Transport
   failures are not retried or routed to another provider.
4. PLAN and REVIEW show actual old/new channel values, model names and every
   affected shared-channel scene. The proposal remains server-owned; the
   browser cannot submit a Context, raw frame, extra action or another model.
5. CONFIRM requires fresh target/shared-impact and external-mute acknowledgments.
   ARM SEND opens an eight-second window; the last click alone transmits. Back
   to Review revokes that arm. Keyboard shortcuts never send device changes.
6. SEND revalidates complete state and every original scene map, applies only
   the reviewed scalars with independent formatted-display/full-state checks,
   checks all eight maps again and returns the original scene. No Store or
   automatic Undo is offered. Unknown outcomes consume the review and latch
   the connection; keep audio muted and inspect before reconnecting.

Scan/review tokens belong to the current connection and expire. A device,
preset or scene change invalidates stale responses. Discard/new requests cannot
be overwritten by a late provider response. Unrelated FM9 and earlier manual
review modes keep their original behavior. The addon is hidden when its mode
is not configured; it reuses existing stages instead of introducing another
application or server instance. English remains the fallback for new strings.

Scan confirmations belong to the preset and scene in the existing-state
metadata itself. Both independent state reads must agree. A metadata target
change clears all confirmations, including before the first scan. Disagreeing
reads disable SCAN and require refreshed state plus fresh confirmation. The
request freezes that confirmed target and rechecks consent after any pending
discard, immediately before posting. No simulated race test recalls hardware
scenes or accesses a preset outside the owner's test range.

Synthetic API/DOM tests, real Chrome with mocked HTTP, selected-provider native
GUI acceptance, independent Axe-Edit and exact installed-source proof are
reported separately. Nothing here certifies physical loudness or audible tone.
