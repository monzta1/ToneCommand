# FW33 effect calibration checkpoint

## Existing Pitch octave pedal: exact MK2 Beta 5 only

In **Controllers**, an existing **Pitch 1, channel A** can now be configured as
an octave pedal. Explicitly choose External 1 or External 2, review, confirm
the target and external mute, then **Send Pitch setup**. Keep the pedal still
while reviewing/sending. Settings are Advanced Whammy, Start 0, Stop +12
semitones, Mix 100%, Level 0dB after bypassed -12dB staging. The native
full-range linear modifier is allocated only if needed and is restricted to
channel A. Auto Engage is Off; SEND activates Pitch in the current scene.
Other scenes using channel A share this voice. A nonmatching existing modifier
curve or other active Pitch modifier is refused, not overwritten.
The starting model must be the measured default Dual Detune or Advanced
Whammy; transitions from other models require separate acceptance.

This is a separate existing-block feature on measured MK2
`33.00-beta5.20261026`, not a generic setter or a new-preset builder capability.
Do not interpret the planning catalog's unsupported Pitch status as a ban on
this explicit controller tool, or this tool as permission to plan unsupported
Pitch insertion. No routing, amp tone, global pedal/CC map, NAM, IR, Store or
other firmware write gate is changed. MK1 and unmeasured firmware remain
blocked for this feature. Reviews expire after 60 seconds and are consumed
before execution. A write whose outcome cannot be proved latches this feature
on the connection; there is no automatic retry, rollback or Undo.

Acceptance on test327: captured model/range/control/mix/level/bypass and native
modifier allocation/source/channel operations, native full-state checks and a
fresh independent Axe-Edit 1.15.02 comparison of both the Pitch voice and its
modifier. The comparison used UI Automation; it is not proof of audible pitch
tracking, physical pedal direction or loudness. The disconnected test fixture
has no playable signal route and was not stored. Presets 326/328 were preserved.
Still pending: physical-pedal/listening acceptance, Pitch placement and normal
multi-scene compiler integration, Auto Engage, other intervals/instances/channels,
and acceptance on other firmware/chassis.

## Current planning vocabulary and execution scope

The route explorer, request-first scene brief and concrete text/NAM designers
now share `devices/axefx3/effect_capabilities.py`. It describes the broader III
effect vocabulary and the actual execution scope for the selected route,
firmware and chassis. It is not a new model/parameter write gate or a live
discovery of every future effect. Its baseline is the III block column in the
[official Blocks Guide](https://www.fractalaudio.com/downloads/manuals/fas-guides/Fractal-Audio-Blocks-Guide.pdf)
of June 2023. NAM and Amp/Cab remain separate foundation choices.

For the previously accepted `33.00-beta.20261006` MK2 builder:

| Route | Configurable effect profiles | Sharing |
| --- | --- | --- |
| AMP/CAB | T808 Mod, Modern VCA Compressor, 10 Band Variable Q (cut-only), Cry Babe wah with selected External 1/2, retained Delay/Chorus models | Drive/Comp/GEQ follow Amp A-D; Wah/Delay/Chorus share A; 1-8 scenes |
| Serial test | Delay and Chorus only; retain models | A; one scene |
| NAM | Delay, Chorus and Reverb; retain effect models | A; one-scene foundation, then up to two scenes |

These facts still require normal target, full-state, modifier, route, level,
review and SEND validation. The separate experimental MK1 builder retains its
own exact-fingerprint, one-scene AMP/CAB/Chorus/Delay/Reverb scope. Declaring MK1
in the main workspace does not enable the MK2 builder. Current Beta 5 normal
app writing is still blocked; the isolated four-value Amp calibration is not
effect-building acceptance. Historical results below are not Beta 5 promotion.

Scene requirements now cover delay/chorus and the broader effect vocabulary,
not just the previous six keys. Required effects chosen for a musical purpose
must survive compilation. Bypassed or dry effects, flat EQ and a Pitch Level
setter do not satisfy the corresponding sonic requirement. A missing effect
uses the existing clarification conversation, without silently replacing it.
No unsupported effect can generate actions through its catalog entry.

Remaining execution work includes Phaser/Flanger/Rotary/Tremolo, musical Pitch,
Volume, Enhancer/Filter/Formant/Gate, additional delay families, Dynamic
Distortion, special-purpose blocks, additional instances/channels and flexible
routing. A block present as a bypassed reserve is not complete voicing support.
Feedback Send/Return, Scene MIDI, external-input routing and loopers require
dedicated validation because they can affect feedback, recordings or external
equipment. Dyna-Cabs remain a separate cabinet-mode roadmap item. Each new
family needs captured encodings, native preservation checks, independent editor
comparison and integration into the normal scene compiler before release.

## Historical exact-build calibration

This is evidence status, not blanket permission to write every effect. The
normal route keeps unvoiced reserve effects bypassed. FM9
permissions, permanent storage allowlists and unknown-outcome behavior are
unchanged. Only the owner's exact FW33 beta/MK2/Windows profile was used.

## Drive1

All87 selector names/ordinals were independently selected in Axe-Edit. A-D basic
gain/tone/level/mix and exact-zero setters were captured on T808 Mod. The fixed
171-step native replay verifies independent numeric displays and complete
unrelated-state preservation. A subsequent separate Axe-Edit comparison confirms
T808 Mod, gain0, tone5, level0, mix100 on each A-D channel, always bypassed.

A reviewed T808 Mod build can represent four voices following Amp A-D and
explicit per-scene activation. It has exact grammar/value/order checks and a
bounded final LEVEL knob0..2.5, not dB or proven unity gain. Exact engage/bypass
is captured on A-D using typed parameter7, not an assumed generic0x0a command.
The actual configured AI's eight-scene design completes384 normal SEND actions
with full-state checks; a separate Axe-Edit pass confirms all eight stored scene
channel/bypass maps and four numeric voices. This narrowly releases T808 Mod
within the reviewed route, not generic Drive models, arbitrary pedal insertion,
physical loudness, audible tone matching or controller behavior. The release
gate still has no GUI/environment override.

## Compressor1

All19 model selectors were captured on A. Modern VCA Compressor basic controls
were measured on A-D, including auto-makeup OFF, auto-attack/release OFF,
threshold, ratio, attack/release time, level and mix, with exact zeros where
applicable. The closed153-step native prefix passes independent display and
full-state checks. No compressor is engaged or enabled in normal planning by
that result. Auto-makeup and transient model defaults require explicit staging;
an attenuation written later cannot protect an earlier model transition.

## Post-EQ

All18 Graphic EQ model choices were captured. Ten-band variable-Q controls and
zero bands were initially captured on A/B and partly C before Windows access
was lost. The owner restored access; C/D and typed bypass transitions were
subsequently captured, with final A-D bands0dB, level-12dB and Q1. The Q law
uses its observed geometric midpoint, not linear normalization. The first
earlier native EQ operation was refused before transmission because
the current channel was C while the capture started on A. The shared calibration
now checks every family's initial context before ANY mutation. No EQ write was
sent in that native pass; no automatic channel correction, retry or rollback
was attempted. PEQ and other effects are not promoted by these partial captures.

## Recorded developer calibration

The developer-only replay binds an immutable closed379-step manifest to quiet
preset322, exact firmware/chassis/grid, all inactive modifiers, fresh complete
state and exact current channel. A failed or unknown result consumes the
operation. It does not expose a general raw setter, model permission or AI
action. Neither calibration nor readback measures audible tone or loudness.

Resume requires an accessible, continuously connected Windows desktop for the
remaining independent Axe-Edit comparisons. No firmware, driver, IR/NAM memory,
global settings or permanent preset Store was changed in this checkpoint.

The expanded native pass completed379/379 with independent numeric/status and
full-state preservation checks, including GEQ Q .5/2/1 and all24 typed bypass
transitions. It ended on322/scene1 with Amp, Drive, Compressor and GEQ bypassed,
all on A, Output-18dB. The MIDI connection closed normally; TC did not Store.
The owner will save the test fixture manually, which is not a TC Store proof.

After the owner resumed testing, the separate editor comparison passes all12
Drive/Compressor/GEQ channel states. Drive then passes actual AI/normal SEND and
its own independent eight-scene editor comparison. Compressor/GEQ still require
their normal planner/executor integration and acceptance at that checkpoint.
The later actual selected-AI536-action normal SEND now passes all eight scenes,
with independent full-state readback and no Store. A subsequent independent
Axe-Edit comparison verifies Compressor/GEQ models, manual modes, values,
channel assignments and bypass in all eight scenes. Modern VCA and10 Band
Variable Q A-D are now released narrowly on the same fixed route, with manual
compressor auto modes OFF and nonpositive EQ gains/levels. PEQ and other model
families remain unmeasured. Physical sound/loudness acceptance is separate.
