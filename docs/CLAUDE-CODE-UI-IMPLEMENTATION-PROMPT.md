# Claude Code implementation prompt

Copy everything below this line into Claude Code from the `fm9-tone` repository root.

---

You are the senior frontend engineer and interaction designer responsible for implementing the ToneCommand desktop control-surface redesign in this repository.

## Objective

Transform ToneCommand into a serious desktop control surface for professional Fractal FM9 guitar hardware while preserving its retro-metal/future-machine identity and every existing capability.

The primary workflow must be unmistakable within five seconds:

**REQUEST → PLAN → REVIEW → CONFIRM → SEND**

ToneCommand is not a chat application or a generic SaaS dashboard. Treat the FM9 as physical hardware under direct human command. AI may propose changes, but a human must review, confirm, and explicitly send them.

## Authoritative design sources

Read these completely before changing code:

1. `docs/UI-REDESIGN-SPEC.md` — authoritative information architecture, dimensions, states, component hierarchy, terminology, safety rules, and acceptance criteria.
2. `docs/img/ui-redesign-review-mockup.png` — visual direction for the Review stage and overall application shell.
3. `docs/INTERFACE.md` — explanation of all existing interface behavior.
4. `README.md` — product principles and safety model.
5. `ARCHITECTURE.md` — backend boundaries and device safety architecture.

If the mockup conflicts with the written specification, follow `docs/UI-REDESIGN-SPEC.md`. The mockup communicates appearance and hierarchy, not exact behavior.

## Before implementation

Audit the current application before editing:

- Read `ui/index.html`, including its CSS, markup, client state, and event handlers.
- Read the relevant routes and response shapes in `server.py`.
- Read all UI, safety, planner, apply, slot, health, recipe, design, modifier, and snapshot tests.
- Inventory every current user-facing function and map it to its destination in section 2 of the specification.
- Check the working tree and preserve all pre-existing user changes. Never overwrite or revert unrelated work.
- Identify whether any project-level `AGENTS.md` adds instructions.

Do not begin with a superficial restyle. This is an information-architecture and interaction-state redesign.

## Non-negotiable product rules

1. Preserve every existing function listed in section 2 of `docs/UI-REDESIGN-SPEC.md`.
2. Preserve the existing backend safety architecture. The planner must never send directly to the FM9.
3. No hardware write may bypass validation, preset pinning, human review, confirmation, snapshot creation, or read-back verification.
4. The word **SEND** is reserved for the final hardware transmission. Replace the current request-composer SEND/ENGAGE meaning with **GENERATE PLAN**.
5. Use these five explicit client stages: Request, Plan, Review, Confirm, Send.
6. Confirm and Send must remain separate states.
7. A final **SEND TO FM9** control may exist only in the armed Confirm state.
8. Sending changes only the edit buffer. It must never store a preset automatically.
9. Rename permanent saving behavior to **STORE PRESET** in the UI. Store, Rename, and Erase must retain separate confirmations and accurate irreversibility warnings.
10. Show affected scenes and shared-channel blast radius before transmission.
11. Disarm confirmation if the plan, preset, scene, link, or hardware target changes.
12. Gig Lock must block transmission and must never be exited automatically.
13. Distinguish `VALID` before transmission from `VERIFIED` after hardware read-back.
14. Never claim audible success. Successful workflows end with **EARS: PENDING**.
15. Offline or last-known hardware data must be visibly stale and must not pass preflight.
16. Preserve automatic Undo snapshots, A/B behavior, model audition, parameter edits, modifiers, Graphic EQ, health scanning, recipes, designs, rig profiles, allowed storage slots, and activity logging.

## Required layout

Implement the fixed desktop shell defined in section 4 of the specification.

At 1440 × 900 CSS pixels, without browser-document scrolling, the screen must show:

- 64px Hardware bar;
- 52px five-stage workflow rail;
- 136px live FM9 context strip containing all eight scenes and the signal-path overview;
- focused stage workspace with left navigation, central work canvas, and right impact/Inspector rail;
- fixed 52px command shelf containing Undo, Compare, Diagnostics, Library, Storage, Activity, and Settings.

The workspace may scroll internally. The Hardware bar, workflow rail, live context, active stage footer, and command shelf must remain visible.

Minimum supported width is 1180px. Do not create a compressed mobile Send workflow. Follow the breakpoint and UI-scaling behavior in sections 14 and 17.

## Required interaction architecture

Remove the top-level `DESIGN WITH AI / MANUAL` division.

- The five-stage rail becomes primary navigation.
- Manual parameter editing becomes a contextual Inspector opened by selecting a signal-chain block.
- Recipes, Designs, Rig Profiles, Diagnostics, Storage, Activity, AI settings, appearance, and safety configuration become command-shelf drawers.
- Only one utility drawer may be open at a time.
- Preserve stage and selection context when a drawer or overlay closes.

Implement each stage exactly as specified:

### Request

- Conversation and clarifications.
- Anchored composer with **GENERATE PLAN**.
- Describe, Source, and conditional Empty Slot modes.
- No more than four example requests in the empty state.
- Source analysis progress remains globally visible and stoppable.
- Empty-slot builds enter the same Plan → Review → Confirm → Send workflow.

### Plan

- Show intent groups and scope, not a wall of raw parameter values.
- Surface grounding, inference, missing information, target mismatch, and validation blockers.
- Provide **REVIEW {N} CHANGES**, **SAVE PLAN FOR LATER**, and **DISCARD**.

### Review

- Implement the exact-change table and filters specified in section 5.3.
- Keep stage actions and impact/preflight information visible while a large plan scrolls internally.
- Expand warnings, failures, topology edits, and modifier assignments by default.
- Collapse safe repetitive changes by intent group.
- Provide a routing-diff overlay for topology changes.

### Confirm

- Make Confirm a full safety stage, not a generic modal.
- Show Target, Scope, Destination, and Recovery facts.
- Require acknowledgement, then **ARM SEND**.
- Armed state exposes **SEND TO FM9** for eight seconds.
- `Esc` disarms.
- Do not use a typed phrase or hold gesture.

### Send

- Show Snapshotting → Transmitting → Read-back Verifying → Complete.
- Stream meaningful per-action progress and retain the complete detail behind disclosure.
- Use green only for read-back-verified outcomes.
- Explain partial failure and recovery accurately.
- Success must state `EDIT BUFFER MODIFIED · PRESET NOT STORED`, Undo availability, and `EARS: PENDING`.

## Visual requirements

Follow section 8 token values and hierarchy.

- Preserve the near-black, blue-black, cold cyan, ultraviolet, amber, green, and red palette.
- Cyan is command/navigation/telemetry.
- Violet is scene, selected hardware context, and modulation.
- Amber is impact/caution/inference.
- Green is only linked or verified success.
- Red is blocking failure or final destructive action.
- Use blackened-steel surfaces, precise 1px borders, squared 2–4px radii, a very subtle engineering grid, and restrained glow.
- Avoid generic rounded cards, excessive gradients, decorative status colors, large ambient glows, oversized whitespace, and tiny low-contrast text.
- Use the exact typography and spacing hierarchy from the specification.
- Use tabular numerals for parameter values.
- Do not depend on externally hosted fonts; use local assets or specified fallbacks.

The existing ToneCommand logo may be reused. Do not replace or reinterpret the brand mark.

## Engineering constraints

- Preserve existing backend endpoints and data contracts unless a change is genuinely required to satisfy the specification.
- Prefer restructuring the client presentation and client state before modifying backend architecture.
- Do not remove safety checks or duplicate safety logic with a weaker client-only version.
- Keep hardware mutations behind existing server-side validation and apply paths.
- Do not invent parameter values, frequency labels, device capabilities, or verification guarantees.
- Reuse existing data, rendering logic, and action handlers where their behavior remains correct.
- Refactor carefully enough that responsibilities are understandable; do not merely hide the old long page with CSS.
- Do not add a large frontend framework unless the repository already uses one or the current architecture makes the redesign impossible without it. Explain and justify any new dependency before adding it.
- Preserve keyboard model audition and preset navigation.
- Commit slider changes according to existing snapshot/write semantics; do not flood the hardware with accidental pointer-move writes.
- Preserve reduced-motion behavior.
- Avoid inline explanatory walls. Put concise safety copy at decision points and details in disclosures.

## Accessibility requirements

Implement section 13 completely:

- full keyboard operation;
- clear focus rings not represented only by glow;
- semantic buttons, tabs, tables, dialogs, and live regions;
- non-color state indicators;
- appropriate focus trapping and restoration;
- minimum 12px functional text at 100% scale;
- WCAG AA contrast;
- reduced motion;
- meaningful but non-noisy announcements for link and transmission state.

`Cmd/Ctrl+Enter` may generate a plan but must never trigger final hardware Send. Final Send has no global shortcut.

## Implementation process

Work in coherent, testable vertical slices rather than changing the entire file blindly.

Recommended order:

1. Fixed app shell and shared visual tokens.
2. Workflow state model and five-stage rail.
3. Persistent Hardware bar and live scene/routing context.
4. Request and Plan stages.
5. Review table, filters, blast radius, and preflight.
6. Confirm arming and invalidation behavior.
7. Send progress, results, and recovery states.
8. Routing-driven parameter Inspector, audition, modifiers, and Graphic EQ.
9. Command shelf and all utility drawers.
10. Offline, dirty-buffer, Gig Lock, storage, and destructive edge cases.
11. Accessibility, scaling, and visual polish.

After each slice:

- run the relevant existing tests;
- add focused tests for new stage and safety behavior;
- inspect the UI at the target viewport;
- verify that no existing capability became unreachable.

Do not delete tests simply because the old layout changed. Update presentation-specific assertions to the new intended behavior and preserve behavioral/safety coverage.

## Required verification

Before declaring completion:

1. Run the complete test suite.
2. Run any UI/static checks already present in the repository.
3. Start the application in its safe simulator/offline mode. Do not require or mutate real FM9 hardware for visual verification.
4. Capture screenshots at:
   - 1440 × 900;
   - 1280 × 800;
   - 1180 × 720;
   - 1440 × 900 at 130% UI scale.
5. Capture at least these application states:
   - Request empty;
   - Request conversation/clarification;
   - Plan summary;
   - Review with blast-radius warnings;
   - Confirm unarmed;
   - Confirm armed;
   - Send in progress;
   - Send successful;
   - Send partial failure;
   - Offline/stale;
   - selected bypassed block Inspector;
   - Graphic EQ Inspector;
   - Storage confirmation.
6. Compare the Review screenshot with `docs/img/ui-redesign-review-mockup.png` for hierarchy and visual character, while following the written spec for exact behavior.
7. Verify every acceptance criterion in section 17 of `docs/UI-REDESIGN-SPEC.md` individually.

If browser automation is available, use it for screenshots and interaction checks. Confirm tab order, Escape behavior, stage gating, confirmation invalidation, drawer exclusivity, large-plan scrolling, and unsupported-width handling.

## Completion report

When finished, report:

- the implemented architecture and key files changed;
- how every old feature maps into the new interface;
- tests added or updated;
- full test results;
- screenshot paths;
- any deliberate deviations from the specification and their reasons;
- any remaining risks involving real hardware that could not be validated in the simulator.

Do not call the work complete if any existing function is missing, any safety gate is weakened, the five-step workflow is unclear, the reference viewport requires document scrolling, or the final hardware Send can be triggered outside the armed Confirm state.

Begin by reading the authoritative files, auditing the current behavior, and writing a short implementation plan. Then implement the redesign fully and verify it.
