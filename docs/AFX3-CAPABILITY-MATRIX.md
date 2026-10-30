# Unofficial FX3 capability matrix

28 October 2026. Retained implementation, shared-interface scope and native
evidence are different. A known name, bulk length, chassis choice or passing
simulator never grants a write capability.

| Exact profile | Full-workspace definitions | Shared interface | Full-workspace write status |
|---|---:|---|---|
|32.06 |75 |Read-only III connection |Retained guarded legacy operations, not every hardware function. |
|33.00-beta.20261006 |83 |Read-only by default; the explicitly enabled MK2 experiment permits one existing Amp1/A Gain or Mid edit through REVIEW/CONFIRM/SEND. |Retained measured operation families, each with its own gates. |
|33.00-beta5.20261026 |0 |Default read-only. Older Amp opt-in still refuses. Separate explicit model0 Gain/Mid experiment has its own native evidence. |General writing blocked. No model selector or whole-rig approval follows from the separate experiment. |
|Unknown response or raw97.00 |0 |Unknown/raw fallback, read-only |No inferred compatibility, verified writes or rename capability. |

The earlier83-definition profile retains approved parent controls and measured
additions. Its historical evidence includes bounded1..8-scene AMP/CAB builds,
336 Amp choices, Legacy CAB selection/mixing, measured effects, controllers
and separately reviewed NAM/Store operations. Each still requires its actual
runtime, target, channel, routing, consent and readback conditions. It does not
approve later firmware, arbitrary graphs or all effect models.

Beta5 evidence is separate: [migration](AFX3-FW33-BETA5.md),
[read-only follow-up](AXEFX3-READONLY.md) and
[closed Amp measurements](AFX3-BETA5-PARAMETER-FAMILIES.md). Until explicitly
released, normal registry/output gates remain closed. Preserve older successful
tests rather than relabeling them as new-build acceptance.

The reviewed-edit bridge is a small manual experiment, not an AI whole-rig
builder. Its environment opt-in is not a firmware override. No fallback
connection, automatic SEND/Undo/Store or general writability is added. The
independent full workspace retains its own capabilities. Do not interchange
its adapter/protocol with `readonly_adapter`/`readonly_protocol` to bypass a
refusal.

## Declared chassis and memory

MK1/MK2 share one control implementation and firmware-specific parameter
definitions. [Central chassis/storage policy](AFX3-SHARED-IMPLEMENTATION.md)
does not grant writer approval; native acceptance remains separately scoped.

| Chassis | Shared name-read range | NAM-era User2 CAB policy | NAM installation acceptance |
|---|---|---|---|
|MK1 |0..511 |Reserved for NAM, not a CAB bank |Not independently verified on MK1. The roadmap's128-slot layout is not MK2 parity. |
|MK2 |0..1023 |Both CAB banks retained; separate NAM memory |Earlier exact-profile Windows/MK2 installer is measured, with separate destination consent and full readback. Not promoted to Beta5 by memory size. |
|Turbo |0..1023 for the declared reader |No inference from capacity |Independent Turbo hardware acceptance required. |

The chassis choice is a declaration, not detection. All1024 MK2 names were
independently compared with an editor export; two leading-space differences
remain visible, not silently normalized. Upper name reads do not authorize
upper-slot Store. Existing preset/CAB/NAM allowlists are unchanged. Name import
is not an IR installation.

## Separate gates

- Normal Beta5 parameters/models/CABs/routes/scenes/controllers/effects/NAM/
  Store need operation-family acceptance.
- MK1/Turbo native parity, audible tone quality, pedal direction and physical
  loudness need the relevant hardware/player, not just software tests.
- Dyna-Cab automation, arbitrary/feedback-prone graphs, every effect instance,
  upper-slot Store, broad audio matching and broader NAM formats are not
  implied by a bounded Legacy build.
- External mute and conservative levels are not a physical limiter. Unknown
  outcomes stop without automatic retry, rollback write or preset reload.

Use [the A-Z ledger](AFX3-COMPLETION-BACKLOG.md) for owners, dependencies and
exit criteria. Implemented, hardware-verified, upstream-reviewed, packaged
and player-accepted are different states.
