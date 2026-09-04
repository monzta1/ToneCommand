# FM9 tone-building rules

The rulebook the planner reads and operates by on every build, and that any
agent working on ToneCommand follows. If a build breaks one of these rules, the
build is wrong, not the rule. These came from real failures (a blind Marco
Sfogli build compared to the pro preset, 2026-09-04); each line is here because
the tool got it wrong once.

## 1. Signal chain order (a rig has a correct flow)
- The chain runs: Input/Gate -> Drive/OD -> Amp -> Cab -> EQ -> Compressor ->
  Modulation -> Delay -> Reverb -> Output.
- Drive/overdrive goes BEFORE the amp (it pushes and tightens the amp).
- Delay goes BEFORE reverb, so the echoes wash into the ambience. Reverb after
  delay, never the reverse.
- A noise gate goes early (before drive/amp), or use the Input block's gate.
- Reverb is last, or nearly last. Time-based effects (delay, reverb) come after
  the amp and cab, not before.
- When adding blocks, place them in this order. When copying blocks from another
  preset, preserve this order, do not just dump settings.

## 2. Scenes are roles, not slots
- A scene is a musical role: clean, rhythm/crunch, or lead (plus variants:
  ambient clean, solo boost, etc.). Decide the roles the request implies first.
- Match the amp to the role, on its own amp channel: a clean-voiced amp for a
  clean scene, a high-gain amp for a lead or rhythm scene. Do NOT take one amp
  and only move the gain knob across roles.
- When comparing or copying across presets, align by ROLE (clean to clean, lead
  to lead), never by channel number. Two presets map scenes to channels
  differently; a channel-for-channel copy lands an effect on the wrong scene.

## 3. Amp and cab do different amounts of the work
- A clean signal is nearly linear, so the CAB / IR carries almost the whole
  clean tone. Get the cab right; the exact amp is forgiving on a clean.
- Distortion is nonlinear and the AMP makes it, not the cab. On a lead the amp's
  gain structure, mids, master and sustain carry the feel, and no cab can fake
  it. Dial the amp for singing sustain.
- Weight your effort by role: clean = get the cab and clean voicing right; lead
  = get the amp's saturation and sustain right; rhythm sits between.
- The cab / IR is the heavy lifter. Use the right IR for the role. The FM9 loads
  any user IR (OwnHammer, York, captured tone-match IRs), not just factory cabs.

## 4. Levels: never ship an inaudible or unbalanced scene
- No scene may be so quiet the player can barely hear it. This is the single
  worst failure: a build that is inaudible is unusable.
- A lightly driven clean amp makes little output, so its LEVEL needs to be UP
  (near 0 or positive), not cut. Do not cut the level of an already-weak scene.
- Balance for equal perceived loudness: rhythm scenes within about 1 dB of each
  other, leads 2-3 dB above, cleans matched so they sit in the same mix.
- Say the level reasoning in the reasons.

## 5. Effects follow the artist's actual style, not a rigid rule
- Do not apply "delay only on leads". Ambient and clean-forward players (Sfogli,
  Gilmour, post-rock) live on delay and reverb in the CLEANS; those scenes
  should be drenched, not dry.
- Set every effect you enable, never merely switch it on: delay gets a time
  (from the tempo: dotted eighth = 45000/bpm ms, quarter = 60000/bpm ms),
  feedback, mix and tone; reverb gets a type, a decay and a mix; modulation gets
  rate and depth.

## 6. Copying / composing from a reference preset
- "Copy the effects from X" means reproduce them faithfully: the same settings
  AND the same signal-chain order AND on the matching scene by role. A
  wire-for-wire dump that ignores order and scene is not a faithful copy.
- Prefer lifting a whole block from a reference the player owns over guessing
  its parameters, especially for complex effects (a stereo clean delay).

## 7. Never invent, never write blind
- Every parameter set must exist in the reference; where you interpret rather
  than report an artist's rig, say so in the reason.
- Nothing reaches flash without read-back verification, and nothing is written
  to a slot outside the store whitelist.
