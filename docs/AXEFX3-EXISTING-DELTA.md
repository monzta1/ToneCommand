# Existing-preset scalar proposal contract

This is the first small extraction of the existing-preset editor from #270.
It accepts a typed musical proposal for all eight existing scenes, compares
it with a host-provided editable surface, and returns a review-only scalar
delta with old/new values and shared-channel scene impact.

## What this slice does

- Reject extra AI fields, duplicate controls, aliasing addresses, non-finite
  values, out-of-range values and no-op/rounding-only changes.
- Derive affected and active scenes from all eight observed maps. A bypassed
  effect or a different channel does not count as an active change. Each scene
  needs active coverage; names alone do not create a distinct voice.
- Preserve Input, Output, Amp Level, expression positions, modifier-owned,
  timing-linked and wet-only controls. Host qualification defaults to false.
- Preserve the original grid, models, cabinets, scene names, channels,
  bypass states, modifiers and every unproposed parameter word as the intended
  execution contract. Neither the input observations nor proposal are mutated.
- Fingerprint the complete supplied context, including opaque observations.
  This fingerprint is not an expiring approval token or a write permission.
- Respect declared Mark I 512-slot and Mark II/Turbo 1024-slot bounds without
  inferring chassis identity or any shared-memory policy.

No device/provider/transport is imported. There are no registered endpoints,
UI activation, generic executor actions, scene recalls, model/cab selection,
block insertion, parameter writes, NAM, global settings, Store or rollback.
Both drafts can be reviewed independently against upstream main.

## Host boundary and later slices

`Context` describes inputs, not their provenance. The future host must obtain
a complete stable snapshot, exact firmware/chassis qualification, all modifier
records, existing models and an externally muted eight-scene survey, and only
then expose independently qualified controls. Never accept that context from
AI output as proof. The AI `Design` schema cannot extend the host surface.

Later contributions must provide the snapshot/survey, qualified control codecs,
minimal-delta executor, full before/after preservation checks and independent
display reads, followed by REVIEW/CONFIRM/SEND wiring, fresh target/mute consent,
single-use expiry and failure latching. None is implied by `executable=False`.
No caller in the shipped app currently imports this planning module.

## Evidence and limitations

This extraction is tested offline with synthetic contexts. It is not an
upstream native execution acceptance. In the larger local integration, an
eight-scene existing Mark II preset was adjusted by eight scalar writes on
33.01.20261031 through the selected AI and normal GUI SEND flow on 1 November
2026. Separate Axe-Edit reads confirmed all eight values, and complete device
reads confirmed no unrequested word or scene-map changes. That evidence
motivates this contract, but does not qualify this port's future executor.

Physical Mark I validation, other firmware identities and a listening/tone-match
assessment remain separate. No private preset payloads, account data, IRs or
NAM captures are included. The existing local user installation is unchanged.
