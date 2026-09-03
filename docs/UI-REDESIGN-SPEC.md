# ToneCommand desktop control surface — implementation specification

Status: design specification only  
Target: ToneCommand for Fractal FM9, desktop browser  
Reference viewport: 1440 × 900 CSS px  
Minimum supported desktop viewport: 1180 × 720 CSS px  
Primary workflow: **REQUEST → PLAN → REVIEW → CONFIRM → SEND**

---

## 1. Product position and design intent

ToneCommand is not a chat page with device controls underneath it. It is a command console for physical guitar hardware. The interface must make four facts legible before any feature detail:

1. which FM9 and preset the operator is commanding;
2. which scene is active and what signal path is live;
3. where the operator is in the five-stage command sequence;
4. whether any action is still a proposal or has crossed the hardware boundary.

The visual character remains retro-metal/future-machine: blackened steel surfaces, cold cyan instrumentation, ultraviolet performance accents, tight monospace labels, restrained glow, and hard-edged control geometry. The redesign removes decorative repetition, oversized empty panels, and the long-document feeling. It should resemble a purpose-built rack controller: persistent status, stable control zones, deliberate arming, and explicit transmission.

The governing sentence is:

> The machine may propose. The human reviews, confirms, and sends.

“SEND” is reserved for the final hardware write. The current command-composer action named SEND must become **GENERATE PLAN** so the word cannot mean both “ask the AI” and “transmit to the FM9.”

---

## 2. Existing capability inventory and destination

No current function is removed. Each is assigned a stable home and a disclosure level.

| Existing function | New location | Default visibility |
|---|---|---|
| Link status and rescan/reconnect | Hardware bar, upper right | Always visible |
| Preset picker, filter, keyboard navigation, rescan | Hardware bar, upper center | Current preset always visible; picker on demand |
| Eight scene selection buttons | Context strip, left rail | Always visible |
| Current-scene indication | Scene switch and workflow context | Always visible |
| Pending-plan blast radius / WILL CHANGE | Scene switch and Review impact card | Always visible when relevant |
| Signal-chain routing grid | Context strip, center | Compact live overview always visible |
| Enlarged routing review | Review workspace overlay | On demand; auto-suggested when topology changes |
| Block bypass/engage | Routing grid and Inspector | Available on block selection |
| Block channel A–D cycling | Routing grid and Inspector | Available on block selection |
| Model labels in routing blocks | Routing grid tooltips/Inspector | Summary on grid, full on selection |
| AI conversation and clarification | Request and Plan stages | Visible only while relevant |
| Example tone requests | Request empty state | First-use/empty state only |
| AI backend/model identity | Request header | Compact chip always visible in Request |
| AI backend settings, key, URL, model, setup | Settings drawer | On demand |
| Text-size controls | Settings > Appearance | On demand; keyboard shortcuts remain possible |
| Gig/performance lockout | Hardware bar | Always visible when enabled; control always reachable |
| Build from video/page/transcript | Request source-mode drawer | On demand |
| Source progress and stop | Global operation strip | While active |
| Stated vs inferred source facts and quotes | Plan evidence drawer | On demand; inference count surfaced |
| Source build questions: scene count and name | Plan requirements card | When required |
| Proposed plan summary | Plan stage | Primary content |
| Exact plan actions | Review change table | Summary first, details available without page scroll |
| Validation errors and warnings | Review issue rail and rows | Always visible when present |
| Topology splice/move details | Review change-row disclosure | On demand unless destructive/high-impact |
| Save plan for later | Plan stage overflow action | On demand |
| Discard plan | Workflow footer | Always visible while plan exists |
| Apply/transmit and streamed progress | Confirm then Send stages | Stage-gated |
| Per-action verification result | Send result table | During and after transmission |
| Empty-slot starting chain | Request quick action / empty-preset state | When current slot is empty |
| Tone recipes: filter, refresh, use | Library drawer > Recipes | On demand |
| Public recipe sharing status | Library drawer > Recipes | Secondary metadata |
| Rig profile export/import/clear | Library drawer > Rig profiles | On demand |
| Offline designed presets: list/send/share/delete | Library drawer > Designs | On demand |
| Plan/design preset-moved checks | Review preflight | Automatic and visible if failed |
| Amp and cab model audition, bank, search, keyboard stepping | Inspector > Amp/Cab picker | On block selection |
| Amp and drive continuous parameters | Inspector > Parameters | On block selection |
| Effects parameters | Inspector > Parameters | On block selection |
| Dynamics and level parameters | Inspector > Parameters | On block selection |
| Graphic EQ faders, curve presets, flatten, output level | Inspector > Graphic EQ | On GEQ block selection |
| Bypassed-block warning and one-click engage | Inspector header | Always visible for bypassed selection |
| Modifier-source badge and locked control | Parameter row | Always visible when modified |
| Assign eligible parameter to Pedal 2 | Parameter-row action | On hover/focus; persistent after assignment |
| Preset health scan and streamed progress | Diagnostics drawer | On demand; summary badge persists |
| Per-finding repair and Fix All | Diagnostics results | When fixable findings exist |
| Undo | Persistent command shelf | Always visible when available |
| Hold/recall A and B snapshots | Compare popover in command shelf | On demand; slot status always visible |
| Save to whitelisted preset slot and refresh names | Storage drawer | On demand |
| Rename selected preset | Storage drawer | Secondary action |
| Permanently erase selected slot | Storage drawer > Danger zone | Deep disclosure with confirmation |
| Store-slot whitelist configuration | Settings > Safety | On demand |
| Event/activity log | Bottom activity drawer | Collapsed by default, badge on new/error |
| Share telemetry/recipe-used reporting | Background behavior | No new chrome unless failed |

---

## 3. Information architecture

### 3.1 Primary layers

The application has five persistent layers, ordered by operational importance:

1. **Hardware bar** — device, preset, mode, and irreversible-state awareness.
2. **Command progress rail** — the five-stage workflow and its current gate.
3. **Live context strip** — scenes and compact routing; the physical state being acted on.
4. **Stage workspace** — one focused task: Request, Plan, Review, Confirm, or Send.
5. **Command shelf** — Undo, Compare, Diagnostics, Library, Storage, Activity, Settings.

The first three layers do not scroll. The stage workspace has an internal scroll region. The command shelf stays fixed at the bottom. The browser document itself must not scroll at the reference viewport.

### 3.2 Mental model

Use these nouns consistently:

- **Request**: the operator’s desired outcome.
- **Plan**: the machine’s interpreted intent and proposed scope.
- **Change**: one concrete action inside a plan.
- **Review**: human inspection of exact changes, impact, and validation.
- **Confirm**: a deliberate safety gate acknowledging target and consequences.
- **Send**: transmission to the FM9 edit buffer with read-back verification.
- **Store**: writing the edit buffer permanently to a preset slot. Never call this Save in UI copy.
- **Snapshot**: reversible edit-buffer capture used by Undo and A/B.

The words **send**, **transmit**, and **write** must not appear on controls before the Confirm stage. “Apply” is avoided because it does not say whether hardware is involved.

### 3.3 Secondary navigation

Remove the top-level **DESIGN WITH AI / MANUAL** tabs. They imply two separate products and force users to remember which side holds a control. Replace them with:

- stage navigation for the command workflow;
- contextual editing through the right-side Inspector;
- utility drawers opened from the command shelf.

Manual changes remain direct edit-buffer operations. Selecting a block in the routing overview opens its Inspector. This aligns controls with the physical signal path instead of with an abstract “Manual” page.

---

## 4. App shell and exact geometry

### 4.1 Reference grid at 1440 × 900

All dimensions are CSS pixels.

| Region | Position and size |
|---|---|
| App shell | `1440 × 900`, overflow hidden |
| Hardware bar | `x 0, y 0, w 1440, h 64` |
| Workflow rail | `x 0, y 64, w 1440, h 52` |
| Live context strip | `x 16, y 128, w 1408, h 136` |
| Stage workspace | `x 16, y 276, w 1408, h 560` |
| Command shelf | `x 0, y 848, w 1440, h 52` |

Global outside inset is `16`. Default inter-region gap is `12`. Panels use `1px` borders. No default panel uses more than `16px` internal padding.

The stage workspace uses this column grid:

| Column | Width | Purpose |
|---|---:|---|
| Stage navigator/context | 224 | Stage-specific summary, counts, filters |
| Gap | 12 | — |
| Primary work canvas | flexible; 804 at reference | Conversation, plan, change table, progress |
| Gap | 12 | — |
| Inspector/impact rail | 356 | Hardware target, impact, validation, block parameters |

At 1180 px viewport width, columns become `184 / 12 / minmax(560, 1fr) / 12 / 320`. At widths below 1180, show a deliberate unsupported-width screen rather than collapsing into a mobile layout; this is a professional desktop surface.

### 4.2 Hardware bar placement

Horizontal sequence:

- `16 × 40` emblem at `x 16, y 12`.
- Wordmark `TONE // COMMAND` starting `x 68`; max width `260`.
- Device target group centered in remaining bar: model chip, preset selector, dirty/edit-buffer badge.
- Right cluster: Gig Lock, connection status, settings icon, each `36–44px` high.

The preset selector is `420 × 36`; it must not resize with preset names. Show editor number first, then name: `265  BASSGUY`. Truncate names after the fixed field. Connection is a status button, not a decorative lamp: `FM9 · LINKED`, `SEARCHING`, or `OFFLINE`.

When the edit buffer differs from stored state, show `EDIT BUFFER · MODIFIED` immediately after the preset. This protects the distinction between sending and storing.

### 4.3 Workflow rail placement

The rail is a single centered sequence, maximum width `920`, height `52`. Each stage is `168 × 36`, connected by a `20px` line:

`01 REQUEST — 02 PLAN — 03 REVIEW — 04 CONFIRM — 05 SEND`

States:

- future: muted outline;
- available: cyan label and border;
- current: cyan fill at 12% plus 2px bottom emitter line;
- complete: cyan check glyph and muted fill;
- blocked: red indicator and short reason in tooltip;
- attention: amber indicator;
- Send complete: green check, never cyan.

Only completed or current stages are clickable. Returning to Request with an existing plan opens a small choice: **CONTINUE PLAN** or **START OVER**. Starting over discards the plan only after confirmation.

### 4.4 Live context strip

The strip is one enclosure titled `LIVE FM9 CONTEXT`, divided into two fixed zones:

- **Scenes:** `396px` wide. Eight scene switches in a `4 × 2` grid, each `88 × 42`, gaps `8`. Each shows number and truncated name. Active is ultraviolet. Affected scenes use amber border/fill and a compact `Δ` badge; the full phrase “WILL CHANGE” appears in Review, not squeezed into the switch.
- **Signal path:** remaining width. Render only occupied blocks and their connections in a fit-to-width schematic. The active signal is cyan, reachable inactive structure is slate, bypassed blocks have dashed borders, and unreachable branches are dimmed. Selected block has ultraviolet outline. Right-aligned actions: **EXPAND** and **FIT**.

Clicking the empty background of the signal path opens expanded review. Clicking a block selects it and opens the Inspector. Clicking the block’s bypass target toggles engage/bypass after a snapshot. Clicking the channel badge cycles A–D after a snapshot. These hit targets must be independent and at least `28 × 28`.

During Review, the strip remains visible and affected scenes update immediately from the pending plan. During Send, changed routing blocks pulse once as their action verifies; do not animate continuously.

---

## 5. Stage specifications

### 5.1 REQUEST

Purpose: state the desired sound and establish the request source. The operator should understand the main action within five seconds.

#### Layout

- Left column: `REQUEST TYPE` with three choices: **DESCRIBE**, **SOURCE**, **EMPTY SLOT**. Only relevant choices show; Empty Slot appears only when the current slot is empty.
- Center canvas: conversation plus composer.
- Right rail: `TARGET` card and `PLANNER` card.

The composer is anchored to the bottom of the center canvas, `min-height 64`, `max-height 132`, with a `GENERATE PLAN` button `152 × 44`. Placeholder: `Describe the result you want to hear…`. Helper text: `No change reaches the FM9 until you review, confirm, and send.`

When empty, center the prompt `WHAT SHOULD THIS RIG SOUND LIKE?` and show no more than four example commands in a `2 × 2` grid. A fifth compact link opens Recipes. Once conversation begins, examples disappear.

Conversation bubbles use at most `680px` line width. Operator messages align right with ultraviolet edge; planner messages align left with cyan edge. Clarifying questions remain in Request and do not advance the workflow. When enough information exists, the primary button becomes **GENERATE PLAN**; it never becomes “Build This.”

#### Source mode

Source mode replaces the text composer with one input and **ANALYZE SOURCE**. Accept YouTube URL, web page, or pasted transcript. While analyzing, show progress in the global operation strip above the command shelf, not inside scrolled content. The stop control is always visible there.

After analysis, show three compact evidence counts: `STATED`, `INFERRED`, `QUOTED`. Detailed evidence stays in a drawer. Questions that materially alter the build—scene count and preset name—appear as required fields before **GENERATE PLAN** enables.

#### Empty-slot mode

Show a hardware diagram for `Input → Amp → Cab → Output`, with copy: `Creates a reversible starting chain in the edit buffer.` Primary action: **PROPOSE STARTING CHAIN**. It enters the same Plan, Review, Confirm, Send sequence; do not perform a separate immediate build path in the UI.

### 5.2 PLAN

Purpose: show what the machine believes the operator asked for before overwhelming them with parameter detail.

#### Center canvas

Top card: `PLAN SUMMARY`, maximum two sentences. Beneath it, group proposed work into 3–7 intent groups such as `VOICE AMP`, `TIGHTEN INPUT`, `ADD AMBIENCE`, `ASSIGN PEDAL 2`, or `BUILD ROUTING`. Each group row is `56px` high and contains:

- intent label;
- plain-language outcome;
- number of concrete changes;
- affected block/channel;
- status: grounded, inferred, or needs input.

Do not show raw old/new values here. The Plan stage answers “what is it trying to do?” not “what byte changes?”

Persistent footer actions:

- left: **DISCARD**;
- secondary overflow: **SAVE PLAN FOR LATER**;
- primary right: **REVIEW 24 CHANGES**.

#### Right rail

`PLAN SCOPE` shows target preset, current scene, affected scenes, blocks touched, topology changes, modifier assignments, and inference count. Any ungrounded or validation-blocking item pins an amber/red card above scope and disables Review until resolved.

Plans loaded from Recipes or Designs enter here, with a source badge (`RECIPE`, `OFFLINE DESIGN`) and the same validation path. A moved or mismatched preset is a blocking red card with **RECHECK TARGET**; never silently retarget.

### 5.3 REVIEW

Purpose: inspect exact changes and their blast radius. This is the densest stage, but it remains scan-first.

#### Left column

Filters with counts:

- All
- Warnings
- Routing
- Amp/Cab
- Effects
- Levels
- Modifiers
- Scene metadata

Below filters, a `VIEW` toggle switches between **BY INTENT** and **BY BLOCK**. Search filters labels and values.

#### Center canvas: change table

Use a sticky header and virtual/internal scrolling. Columns:

| Column | Width | Content |
|---|---:|---|
| Status | 32 | validated/warning/error icon |
| Target | 156 | block instance + channel or preset metadata |
| Parameter/action | flexible, min 220 | human-readable name |
| Before | 132 | existing value or `—` for create |
| After | 132 | proposed value or `—` for remove |
| Impact | 92 | affected-scene count or topology tag |
| Detail | 32 | disclosure chevron |

Base row height is `48`; expanded row adds only the necessary rationale, validation message, provenance, topology splice notes, or modifier details. Changed values use tabular numerals. Before is muted; After is cyan. Warnings are amber; blocking failures red. Green is not used until a write verifies.

Group headers are `32px` sticky rows. Large plans default collapsed by intent group except the first group and all warning/error groups. The table footer remains fixed and states `24 CHANGES · 3 SCENES · EDIT BUFFER ONLY`.

#### Right rail: impact and preflight

Order is fixed:

1. `HARDWARE TARGET`: FM9, preset number/name, active scene.
2. `BLAST RADIUS`: scene chips at full legibility, with channel-sharing reason.
3. `PREFLIGHT`: validation, preset pin, link state, snapshot readiness.
4. `REVERSIBILITY`: `Undo available after send`; explicit note if any proposed operation is not undo-covered.

Topology changes automatically offer **EXPAND ROUTING DIFF**, which overlays before/after schematics. Source-derived plans offer **VIEW EVIDENCE** beneath Preflight.

Footer primary action: **CONTINUE TO CONFIRM**. Disabled if any blocking failure exists. Footer secondary: **BACK TO PLAN**. Discard remains available at far left.

### 5.4 CONFIRM

Purpose: create a deliberate human safety pause without turning it into a generic modal.

Confirm occupies the full center canvas and right rail; background context remains visible but subdued. It is not a small modal.

Show exactly four confirmation facts in a `2 × 2` matrix:

- **TARGET** — `FM9 · Preset 265 BASSGUY`
- **SCOPE** — `24 changes across 3 scenes`
- **DESTINATION** — `EDIT BUFFER · NOT STORED`
- **RECOVERY** — `Automatic snapshot ready · Undo available`

Below, show a high-prominence blast-radius line: `SCENES 1, 3, AND 5 WILL CHANGE BECAUSE THEY SHARE CHANNEL A.`

The confirmation control is an arm-and-send sequence inside this stage:

1. checkbox-like guarded control: `I reviewed the target and affected scenes`;
2. once checked, the primary **ARM SEND** button enables;
3. activating it changes the button area for eight seconds to **SEND TO FM9**, with a visible countdown ring and `Esc to disarm`;
4. clicking **SEND TO FM9** advances to Send and begins transmission.

Do not require typing text. Do not use a hold gesture, which is inaccessible and ambiguous with browser/device input. Disarm automatically if the preset, scene, link, or plan changes.

If Gig Lock is active, Confirm explains that writes are blocked and offers **EXIT GIG LOCK** as a separate deliberate action; it never exits automatically.

### 5.5 SEND

Purpose: make hardware transmission observable and verification unambiguous.

#### Center canvas

Header state progresses through:

`SNAPSHOTTING → TRANSMITTING → READ-BACK VERIFYING → COMPLETE`

Use one segmented progress bar whose segment count equals actions, plus numeric copy `17 / 24 VERIFIED`. Below it, show only the currently active action and the five most recent results; the complete action log is available in a disclosure.

The Stop control remains fixed and reads **STOP AFTER CURRENT ACTION** unless the transport can safely cancel the current operation. Copy must match actual cancellation behavior.

Result states:

- queued: slate dot;
- transmitting: cyan animated sweep;
- verified: green check;
- warning/inaudible verification limit: amber diamond;
- failed: red stop icon.

On success, display:

`24 OF 24 CHANGES VERIFIED`  
`FM9 EDIT BUFFER MODIFIED · PRESET NOT STORED`  
`EARS: PENDING`

Primary next action: **AUDITION ON FM9** returns focus to the live context with Undo and Compare prominent. Secondary: **STORE PRESET…** opens Storage; never store automatically. Tertiary: **NEW REQUEST**.

On partial failure, preserve verified/failed grouping, explain whether Undo restores the pre-send snapshot, and make **UNDO TRANSMISSION** the primary safe action when available. Never use a success-colored overall state when even one action failed.

---

## 6. Contextual Inspector

The Inspector occupies the right column whenever a routing block is selected outside Confirm/Send. It replaces the stage’s ordinary right rail temporarily, with a breadcrumb back to `PLAN SCOPE` or `IMPACT`.

### 6.1 Inspector header

Height `64`. Show block family and instance (`AMP 1`), channel badge (`A`), engaged/bypassed state, and close button. Channel and bypass controls are explicit segmented controls, not hidden click regions.

If bypassed, place an amber banner immediately beneath header: `BYPASSED · CHANGES WILL NOT BE AUDIBLE`, with **ENGAGE BLOCK**. If the block is not on the live path, use neutral slate: `NOT REACHED IN THIS SCENE`.

### 6.2 Sections

Sections follow signal/usage order and use one-open-at-a-time disclosure at constrained height:

1. Model/Type
2. Primary controls
3. Tone controls
4. Level/Dynamics
5. Modifiers
6. Advanced

The open section scrolls internally. Primary controls for Amp, Drive, Delay, Reverb, and common effects should be curated from existing metadata; every remaining supported parameter remains under Advanced.

### 6.3 Parameter row

Row height `44`; label width `112`; control flexible; value field `64`; action target `28`. Sliders must include keyboard operation and a double-click/reset control. Do not send continuously on pointer move: preview locally while dragging and commit on pointer release/keyboard settle, matching current snapshot/write semantics.

States:

- default: cyan active track, slate remainder;
- hover: brighter track, visible reset and Pedal 2 actions;
- focus: `2px` cyan focus ring outside the row;
- dragging: value field gains cyan outline and tabular live value;
- pending: small cyan outbound indicator until read-back;
- verified: one-time green flash, 600 ms;
- failed: red row outline and inline error;
- disabled/unavailable: 45% opacity, reason tooltip;
- modifier-driven: slider locked, ultraviolet source badge (`PEDAL 2`, `LFO`, `ENVELOPE`), stored value de-emphasized;
- bypassed block: controls remain operable but carry an amber rail and the block warning persists.

Pedal 2 assignment appears as a `P2` target on hover and keyboard focus. Assigned state remains ultraviolet and names the source. Pedal 1 is never offered.

### 6.4 Amp/cab audition

Model picker opens a `520 × 520` anchored panel containing:

- fixed search input, 40 high;
- bank selector, 36 high;
- virtualized results, 376 high;
- fixed footer with count, current item, and keyboard hint.

Up/Down auditions the previous/next filtered item, Enter commits/keeps the current item, Esc closes. Every audition takes part in Undo as current behavior does. Search matches name and description. Cab results show ordinal, name, and physical description on two lines; amp results show ordinal and name.

### 6.5 Graphic EQ

Selecting a GEQ block uses a wide Inspector overlay (`720px`) because its shape needs width. Ten vertical faders occupy `600 × 224`; zero line remains visible across the full plot. Region labels form a `5 × 1` strip beneath. Curve picker and **FLATTEN** sit in a 44px toolbar above. Output level is a horizontal control below. Frequency labels are not invented; retain numbered bands and truthful region labels.

---

## 7. Utility drawers and command shelf

### 7.1 Persistent command shelf

Left to right:

- **UNDO** plus one-line last-action label;
- **COMPARE A/B** with filled/empty indicators;
- flexible spacer;
- Diagnostics with finding-count badge;
- Library;
- Storage;
- Activity with unread/error badge;
- Settings.

Shelf controls are `40px` high with `12px` horizontal padding. Undo is the only filled shelf control when available. If a transmission just completed, Undo receives a restrained cyan outline for 10 seconds, not animation.

Only one utility drawer may be open. Drawers rise from the shelf to a maximum height of `520` and do not cover the Hardware bar, workflow rail, or live context strip.

### 7.2 Compare drawer

Width `420`, anchored left. Show Snapshot A and B as two rows with capture time, preset/scene identity, and **HOLD** or **RECALL**. Recalling one automatically captures the opposite state as current behavior does; state this inline. Disable recall if the snapshot target is incompatible and explain why.

### 7.3 Diagnostics drawer

Width `720`. Header action **SCAN ALL SCENES** and warning: `Changes scenes and may produce sound for several seconds.` Stream progress by scene. Results table includes scene, live-path result, amp level, volume gain, duplicate status, and findings. Always end with `EARS: PENDING`.

Fix actions create a plan and enter Review; they do not bypass the five-stage workflow. **FIX ALL** is present only when every selected finding has a validated repair. Rescan-only findings say **RESCAN**.

### 7.4 Library drawer

Width `840`. Three tabs: Recipes, Designs, Rig Profiles.

- Recipes: search, refresh, source/author metadata, action count, **PROPOSE**.
- Designs: target profile, action/warning counts, created date, **OPEN PLAN**, Share, Delete in overflow.
- Rig Profiles: current active profile, **EXPORT MY RIG**, **IMPORT PROFILE**, **RETURN TO MY RIG**.

Opening a recipe/design closes the drawer and enters Plan. Deleting a design requires a compact confirmation within the row.

### 7.5 Storage drawer

Width `640`. Rename this concept everywhere from Save to **STORE PRESET** because it writes flash.

Top safety banner: `PERMANENT SLOT WRITE · UNDO DOES NOT COVER STORAGE`.

Primary section:

- target slot selector containing only whitelisted slots;
- wire and FM9-Edit numbers shown together;
- current stored name;
- modified edit-buffer source;
- **RELOAD SLOT NAMES** secondary action;
- **REVIEW STORE** primary action.

Review Store opens a dedicated confirmation inside the drawer stating source preset, destination slot, destination’s current name, and irreversibility. Final action: **OVERWRITE SLOT 265**.

Rename is a separate section and clearly states that renaming stores the preset. Erase lives in a collapsed `DANGER ZONE` at the bottom. Opening it reveals **ERASE SLOT…**; final confirmation repeats slot number and current name. Do not place Store, Rename, and Erase at equal visual weight.

If no whitelist exists, replace controls with explanatory copy and **CONFIGURE ALLOWED SLOTS** linking to Settings > Safety.

### 7.6 Activity drawer

Width `720`. Show timestamp, category, action, target, result. Filters: All, Hardware, Planning, Safety, Errors. Empty state is one sentence; remove the current marketing list from the operational log. Retain downloadable/copyable diagnostic detail if already supported later, but do not add it as a prerequisite.

### 7.7 Settings drawer

Width `560`. Sections:

- AI backend: provider, preset service, base URL where relevant, model, key state, setup flow.
- Safety: allowed store-slot specification, Gig Lock explanation.
- Appearance: UI scale with minus/reset/plus and displayed percentage; reduced motion follows OS.
- Connection: reconnect/rescan and detected device details.

Dangerous or credential-clearing actions use secondary disclosure. **CLEAR KEY** requires confirmation but does not use red as a decorative accent.

---

## 8. Visual system

### 8.1 Color tokens

| Token | Value | Use |
|---|---|---|
| `void-950` | `#05080D` | app background |
| `steel-900` | `#09111B` | primary surface |
| `steel-850` | `#0D1825` | raised surface |
| `steel-700` | `#183047` | borders/dividers |
| `text-100` | `#D7E6F0` | primary text |
| `text-300` | `#9AB0C0` | secondary text |
| `text-500` | `#688096` | tertiary metadata; minimum contrast must still pass |
| `command-400` | `#2FE6FF` | navigation, active controls, telemetry |
| `command-700` | `#176F82` | cyan borders/tracks |
| `scene-400` | `#B98CFF` | scenes, selected hardware context, modifiers |
| `warning-400` | `#FFB454` | impact, caution, inferences |
| `danger-400` | `#FF5470` | blocking errors/destructive actions |
| `verified-400` | `#3DFFA0` | linked/verified/success only |

Green must never style a control before the outcome is verified. Amber is semantic, not ornamental. Violet belongs to performance state and external modulation, not general navigation. Cyan glow is capped at `16px` blur and 24% opacity; large ambient panel glows are removed.

### 8.2 Surface language

- Radius: `2px` for chips/fields, `4px` for panels/drawers, never pill-shaped except status dots.
- Border: `1px steel-700`; selected surface uses `1px command-700` plus inner top highlight.
- Background grid: 48px grid at no more than 2.5% cyan opacity, visible only on app background, never through work surfaces.
- Corners may use small clipped/notched treatment on major panels, maximum `8px`; do not repeat on every row.
- Texture/noise is optional but must remain under 1.5% opacity and never reduce text clarity.

### 8.3 Typography

Use two families:

- Display/labels: `Rajdhani` 600 if bundled locally; fallback `Arial Narrow`, sans-serif. Do not introduce a network dependency solely for this face.
- Data/body: `IBM Plex Mono` 400/500 if bundled locally; fallback `SFMono-Regular, Menlo, Consolas, monospace`.

| Role | Size / line | Weight | Tracking | Case |
|---|---|---:|---:|---|
| Product mark | 22 / 24 | 600 | 0.28em | uppercase |
| Stage title | 20 / 24 | 600 | 0.12em | uppercase |
| Panel title | 14 / 18 | 600 | 0.16em | uppercase |
| Body | 14 / 21 | 400 | 0 | sentence |
| Control | 13 / 16 | 500 | 0.08em | action labels uppercase |
| Data value | 13 / 18 | 500 | 0.02em | as entered |
| Metadata | 12 / 16 | 400 | 0.04em | sentence/labels |
| Badge | 11 / 14 | 600 | 0.10em | uppercase |

Minimum functional text is 12px at 100% UI scale. Values use tabular numerals. Long explanatory paragraphs are replaced with short labels plus disclosure/help; line length is capped at 72 characters in drawers and 84 in stage content.

### 8.4 Spacing and sizing tokens

Base unit: `4px`.

- `space-1 4`
- `space-2 8`
- `space-3 12`
- `space-4 16`
- `space-5 20`
- `space-6 24`
- `space-8 32`

Interactive target minimum is `32 × 32`; primary buttons are at least `44px` high. Dense tables may use `28px` icon targets only when the whole `48px` row is clickable and keyboard accessible.

---

## 9. Interaction state system

Every interactive component implements these common states: default, hover, keyboard focus, pressed, disabled, busy, success, warning, and error where meaningful.

### 9.1 Buttons

- Default primary: cyan border/text, 8% cyan fill.
- Hover: 14% fill, no movement; shadow increases slightly.
- Pressed: 20% fill and inset highlight; no scale animation.
- Focus: `2px` outer cyan ring with `2px` offset.
- Disabled: 42% opacity plus a visible reason in adjacent text/tooltip.
- Busy: label becomes a concrete verb (`ANALYZING`, `VALIDATING`); spinner precedes label.
- Destructive: red outline only at the final destructive gate.
- Verified result: green status treatment, not a reusable “green primary button.”

### 9.2 Fields and selectors

- Height `36`, primary composer `44+`.
- Default border steel-700; hover steel-500; focus command-400.
- Error has red border and inline message; warning has amber message without replacing focus outline.
- Popovers preserve their size while filtering so targets do not move.
- Search results keep keyboard cursor distinct from selected/current hardware item.

### 9.3 Loading and streaming

Never block the entire shell for background work. A `40px` global operation strip appears immediately above the command shelf with operation name, phase, elapsed time when useful, progress, and Stop. Hardware context remains interactive only where safe. Controls that would invalidate the active operation disable with reasons.

Use skeletons only for initial library/table load. For hardware reads, use explicit words: `READING PRESETS`, `SCANNING SCENE 3`, `VERIFYING AMP 1 / BASS`.

### 9.4 Offline and reconnection

When offline:

- Hardware bar turns connection status red.
- Last-known preset/scenes/path remain visible but receive a `STALE · LAST READ 14:32:08` overlay.
- Request, source analysis, recipes, and offline designs remain usable.
- Any stage that requires current hardware state is blocked with a direct **RECONNECT** action.
- Never present last-known values as live.

### 9.5 Dirty state and navigation protection

An edit-buffer dirty badge persists after any direct edit or Send. Changing presets while dirty opens a compact warning that the unsaved buffer will be discarded, offering **STAY** and **LOAD PRESET**. Storage is optional, not pressured. Browser unload protection applies while an unsent plan or active transmission exists.

---

## 10. Progressive disclosure rules

1. Always show hardware target, connection, active scene, live path, workflow stage, and Undo availability.
2. Show intent before parameters: Plan summarizes; Review enumerates.
3. Show all errors and warnings without requiring disclosure.
4. Show blast radius whenever a plan or direct edit affects shared channels.
5. Collapse safe repetitive changes; expand warnings, topology edits, modifier assignments, and irreversible actions.
6. Keep infrequent systems—Recipes, Designs, Profiles, Diagnostics, Storage, Activity, Settings—in drawers, never stacked in the primary page.
7. Block selection reveals parameters; no block selection means no parameter wall.
8. Advanced parameters are one additional disclosure from primary controls, not a separate navigation destination.
9. Destructive storage actions require two levels: enter Danger Zone, then explicit target confirmation.
10. Explanatory copy appears at the decision point and disappears once understood; do not repeat edit-buffer disclaimers in every panel. Persistent destination badges carry that meaning.
11. During a long operation, show current phase and recent events; keep full logs collapsed.
12. Preserve operator context when drawers close, stages move backward, or routing expands.

---

## 11. Component hierarchy

```text
ToneCommandApp
├── HardwareBar
│   ├── BrandMark
│   ├── DeviceTarget
│   ├── PresetSelector
│   │   └── PresetPickerPopover
│   ├── EditBufferStatus
│   ├── GigLockControl
│   ├── ConnectionControl
│   └── SettingsTrigger
├── CommandWorkflowRail
│   └── WorkflowStage × 5
├── LiveContextStrip
│   ├── SceneBank
│   │   └── SceneSwitch × 8
│   └── SignalPathOverview
│       ├── RoutingCanvas
│       ├── RoutingBlock × n
│       │   ├── BypassTarget
│       │   └── ChannelTarget
│       └── RoutingViewportControls
├── StageWorkspace
│   ├── StageSideNav
│   ├── StageCanvas
│   │   ├── RequestStage
│   │   │   ├── Conversation
│   │   │   ├── RequestExamples
│   │   │   ├── RequestComposer
│   │   │   └── SourceEvidence
│   │   ├── PlanStage
│   │   │   ├── PlanSummary
│   │   │   └── IntentGroupList
│   │   ├── ReviewStage
│   │   │   ├── ChangeTable
│   │   │   └── RoutingDiffOverlay
│   │   ├── ConfirmStage
│   │   │   ├── ConfirmationFacts
│   │   │   ├── HumanAcknowledgement
│   │   │   └── ArmedSendControl
│   │   └── SendStage
│   │       ├── TransmissionProgress
│   │       ├── RecentActionResults
│   │       └── SendOutcome
│   ├── StageRail
│   │   ├── TargetCard
│   │   ├── ScopeCard
│   │   ├── BlastRadiusCard
│   │   └── PreflightCard
│   └── StageFooter
├── ContextInspector
│   ├── BlockHeader
│   ├── BlockStateBanner
│   ├── ModelPicker
│   ├── ParameterSections
│   │   └── ParameterRow × n
│   └── GraphicEqSurface
├── GlobalOperationStrip
├── CommandShelf
│   ├── UndoControl
│   ├── CompareControl
│   └── UtilityTriggers
└── UtilityDrawer
    ├── CompareDrawer
    ├── DiagnosticsDrawer
    ├── LibraryDrawer
    ├── StorageDrawer
    ├── ActivityDrawer
    └── SettingsDrawer
```

---

## 12. Exact copy and terminology

Use these primary labels exactly:

- Request composer: **GENERATE PLAN**
- Source action: **ANALYZE SOURCE**
- Plan advancement: **REVIEW {N} CHANGES**
- Review advancement: **CONTINUE TO CONFIRM**
- Confirm first gate: **ARM SEND**
- Final hardware action: **SEND TO FM9**
- Persistent-storage entry: **STORE PRESET…**
- Final storage action: **OVERWRITE SLOT {N}**
- Routing state: **ENGAGED**, **BYPASSED**, **NOT REACHED**
- Successful write: **VERIFIED**
- Human verification limit: **EARS: PENDING**
- Reversible target: **EDIT BUFFER · NOT STORED**
- Irreversible target: **PERMANENT SLOT WRITE**

Avoid: Engage for AI submission, Apply, Execute, Save when storage is meant, Verified for merely planned/validated work, and generic “Something went wrong.”

Errors name the failed object and next safe action: `AMP 1 / BASS DID NOT VERIFY. THE PRE-SEND SNAPSHOT IS READY.`

---

## 13. Keyboard and accessibility requirements

- Full workflow operable without pointer.
- `Cmd/Ctrl+Enter`: Generate Plan in Request; never Send to hardware.
- Final Send has no global keyboard shortcut.
- `/`: focus active stage search when present.
- `Esc`: close popover/drawer/overlay, or disarm Send; never discard a plan silently.
- Arrow keys navigate preset/model lists; Enter selects; Esc returns focus to trigger.
- Scene switches use arrow-key roving focus and Enter/Space activation.
- Routing blocks participate in logical tab order; internal bypass/channel targets have names.
- All state colors pair with text or icon shape.
- Focus is never represented only by glow.
- Respect `prefers-reduced-motion`; warning visibility cannot depend on pulsing.
- Live regions announce connection changes, transmission progress at meaningful intervals, and final verification results without announcing every slider tick.
- Modals/overlays trap focus and restore it to their trigger.
- Minimum text contrast is WCAG AA; target contrast for primary data is 7:1.

---

## 14. Responsive and density behavior

This specification is desktop-first and intentionally does not create a phone editor for performance hardware.

- `≥1440`: reference geometry.
- `1280–1439`: right rail `332`, left `200`; context scene zone `364`; typography unchanged.
- `1180–1279`: right rail `320`, left `184`; compact stage labels retain full words; hardware wordmark may collapse to emblem plus `TONECOMMAND`.
- `<1180`: show a centered requirement: `ToneCommand needs at least 1180px of desktop width for safe hardware review.` Offer no compressed Send workflow.
- Height `<720`: context strip collapses to `104px`, scenes become `36px` high, workspace remains at least `456px`; utility drawers cap at available workspace height.

UI scaling ranges from 90% to 130% in 10% increments. At 120–130%, the left stage navigator may become an overlay filter drawer, but the Review impact rail stays visible. Never shrink text to preserve columns.

---

## 15. Placement rationale

- Hardware status sits highest because every action is relative to a physical target; it must be read before content.
- The five-stage rail sits above the live context because it explains the command state while the context explains the hardware state.
- Scenes and signal path stay persistent because sound and blast radius are scene-dependent; hiding them during Review would conceal the most important consequence.
- Request occupies the center rather than the top of a long page because it is the current operation, not one of many panels.
- Exact changes wait until Review because parameters are evidence for a decision, not the entry point to forming intent.
- Blast radius lives both in scene hardware context and the Review rail because it must be detectable peripherally and explainable explicitly.
- Confirm is a full stage because crossing from proposal to hardware is the product’s defining safety boundary.
- Send is distinct from Confirm so the operator can see transmission and verification as an observable hardware process, not a button toast.
- Manual controls attach to selected routing blocks because guitarists reason along the signal chain; a generic Manual tab loses that physical mapping.
- Undo stays fixed at the bottom because it is the most important recovery action and should never depend on scroll or stage.
- Storage is separated from Send because edit-buffer audition and permanent flash writes have different risk and reversibility.
- Logs, libraries, profiles, and setup are drawers because they support the command loop but are not steps in it.

---

## 16. State transitions and safety invariants

```text
REQUEST
  ├─ insufficient detail → clarification → REQUEST
  └─ generate → PLAN

PLAN
  ├─ needs input/validation failure → PLAN blocked
  ├─ edit request → REQUEST with context preserved
  └─ review → REVIEW

REVIEW
  ├─ blocking error → REVIEW blocked
  ├─ change target/preset → invalidate plan → PLAN
  └─ continue → CONFIRM

CONFIRM
  ├─ target/link/plan changes → disarm → REVIEW
  ├─ back → REVIEW
  └─ acknowledge → arm → send → SEND

SEND
  ├─ success → AUDITION state
  ├─ partial/failed → RECOVERY state
  └─ store requested → STORAGE drawer and separate confirmation
```

Invariants:

1. No planner response can call the hardware transport directly.
2. Every plan is pinned to preset identity and rechecked before Send.
3. Any hardware-affecting control captures a snapshot before mutation.
4. A plan cannot advance past Review with blocking validation errors.
5. Confirm disarms on any target, link, scene, or plan mutation.
6. Store and Erase are never part of a normal Send plan.
7. Whitelisted slots are the only storage targets presented.
8. Read-back success is named Verified; validation before transmission is named Valid.
9. Audible success is never claimed by software; every final ladder ends at Ears: Pending.
10. Offline/last-known hardware data is visibly stale and cannot satisfy preflight.

---

## 17. Implementation acceptance criteria

The implementing agent should consider the redesign complete only when all of the following are demonstrable:

- At 1440 × 900, the full Hardware bar, five-stage rail, all eight scenes, signal-path overview, stage footer, and command shelf are visible without document scrolling.
- A first-time user can identify the sequence Request → Plan → Review → Confirm → Send without opening help.
- The Request action does not use the word Send.
- Review can inspect a 140-change plan while its Continue/Back/Discard actions and impact rail remain visible.
- Affected scenes are visible before hardware transmission.
- No final Send control exists outside the armed Confirm state.
- Direct block edits clearly target the edit buffer and retain Undo behavior.
- Amp and cab audition remains searchable and keyboard-steppable.
- All supported parameters remain reachable through the Inspector, including Graphic EQ and Pedal 2 modifier assignment.
- Offline state distinguishes stale data from live data.
- Gig Lock blocks transmission and cannot be exited implicitly.
- Store, Rename, and Erase have distinct hierarchy and accurate irreversibility copy.
- Health scan, recipes, offline designs, rig profiles, A/B snapshots, AI setup, allowed slots, and activity log remain reachable in no more than two actions from the shelf.
- Keyboard focus, non-color state cues, reduced motion, and 12px minimum text are verified.
- Successful transmission reports edit-buffer state, read-back verification, Undo readiness, and `EARS: PENDING`.

---

## 18. Recommended implementation sequence for the coding agent

This is sequencing guidance, not authorization to change code in this design pass.

1. Introduce the fixed shell, workflow state model, and semantic terminology without changing backend behavior.
2. Move scenes/routing into the persistent context strip and Undo/utilities into the shelf.
3. Split the current command/plan/apply behavior into Request, Plan, Review, Confirm, and Send render states.
4. Convert manual panels into the routing-driven Inspector while preserving existing parameter metadata and action handlers.
5. Move Recipes, Designs, Profiles, Health, Storage, Activity, and AI setup into utility drawers.
6. Add armed confirmation, preflight invalidation, stale/offline presentation, and dirty-buffer navigation protection.
7. Complete keyboard/accessibility behavior and run visual checks at 1440 × 900, 1280 × 800, 1180 × 720, and 130% UI scale.

The backend API surface can remain intact for the first implementation pass. The main architectural change is presentation and client state: one physical target, one stage at a time, one explicit crossing into hardware.
