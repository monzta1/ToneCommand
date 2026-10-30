# Scene goals and listening feedback

Every new FX3 design supplies the requested musical target, role and intended
realization for every scene. This applies to songs, mixed styles, clean/crunch
switches and listening adjustments, not a hardcoded artist or album profile.
Historical designs remain readable but are marked as lacking recorded goals.

The compiler checks actual stored settings, not just scene names or AI prose:

- A promised base-tone difference cannot be only an amp-level, name or delay
  change. Intentional sharing is allowed; identical sounds are not always wrong.
- An effects contrast must change active effects, not bypassed settings only.
- Small knob-only differences with the same amp/cab produce an explicit warning,
  not a supposed numerical proof of audible contrast or stylistic accuracy.
- Explicit required Drive, post-EQ, reverb, wah controller or pitch cannot
  silently disappear from the executable design. Unsupported requirements fail
  before sending instead of being described as completed.

The plan shows goals, explanations and real scene/channel assignments. The AI
still interprets the request: these structural checks cannot prove that its
musical interpretation is correct, detect every semantic omission or replace
a listening test. Technical readback and audible quality are separate.

## Verified tools and channel limits

FW32.06 retains its existing verified model/cab/effect vocabulary and allocates
up to eight scenes to four identical-setting channels per block. No mandatory
rhythm/solo pairing is imposed by its musical design instructions.

Exact FW33/MK2 AMP/CAB still requires the measured fixed 14-block route and
eight scenes. Four voice slots exist, not eight amp channels. Each scene now
explicitly selects a measured Amp A-D and Cab A-D independently. Scene1 uses
Amp/Cab A, the known review starting point. Historical `albums`/lead/solo schema
fields are compatibility data; `scene_layout` determines actual scene roles.
The exact ordered action grammar still protects staging, bypassed reserves,
Output -18dB, bounds, single-use permits and the final eight-scene survey.

Only the two measured Amp1 models and two Factory2 Legacy IR1 selections are
selectable here. Amp gain, bass, mid, treble, master, depth, presence and level
are available on A-D. Delay/Chorus settings share A, with per-scene bypass.
User-bank selector writes, additional model families, Drive/post-EQ voicing,
new controllers and arbitrary graphs are NOT enabled by scene intent or by
copying FM9 constants. Further independent hardware measurements are needed.
NAM and serial modes retain their existing narrower capabilities and limits.

## After a listening test

After a successful eligible normal SEND, use **BIJSTUREN NA LUISTERTEST**. Select the
scenes to change and describe what you hear, what should change and what should
remain. For example: more attack definition, same gain, no extra loudness.

The previous full design is retained for this running TC connection only. The
server binds it to verified device state, not a user-supplied design or claim.
After restart/reconnection or unrelated hardware changes, TC refuses an unknown
baseline instead of guessing. Multi-scene refinement requires the complete
final scene survey, currently the bounded FW33 eight-scene AMP/CAB route.
Single-scene designs can refine their current state; other multi-scene modes
do not yet issue a refinement token. Goals and design checks still apply to
those modes. This feature does not yet recover a design for an
arbitrary older stored preset. For FW33 AMP/CAB select scene1 through the normal
muted navigation confirmation before generating the adjustment. Scene switching
never occurs secretly during planning.

An adjustment returns a complete proposal but protects the compiled settings
of all unselected scenes, including shared effect settings even when bypassed.
Changing a shared amp for scene1 may also affect scene5; TC must find an available
independent configuration or refuse unless both scenes were explicitly selected.
The preset name, route and scene count remain unchanged. New text without a
real settings change is not accepted as a tweak. The confirmation identifies
this as a full verified re-application, not a minimal-write or instant patch.

Read the proposal, mute externally, review and confirm SEND again. Any failed
verification stops without a write retry or automatic rollback. Permanent
Store is still separate. Audition afterwards at low physical volume and assess
the requested tone and balance yourself. There is no automatic audio limiter,
isolated-guitar listening, exact recording-match proof or physical pedal test.

## Recorded acceptance, 2026-10-16

The actual configured selected AI produced a general eight-scene design through
TC's registered plan/review/SEND API on an empty authorized test preset322.
Its Amp/Cab mapping was A,B,C,D,A,B,C,D, not mandatory album pairs. The first
SEND completed275 actions and the eight-scene final survey. A separate native
survey confirmed channel assignments and all eight amp display values per
scene. This was not a hand-authored replacement for the AI design.

A second actual AI request increased only shared voice A gain by0.5 for scenes
1/5. The compiler verified preservation of scenes2/3/4/6/7/8 before the normal
adjustment SEND completed263 actions and another full scene survey. No Store
or NAM/IR-memory operation was performed. Explicit end-of-test navigation
returned to reference328/scene7 and complete snapshot equality with the initial
state passed. Reference326 was not selected or written.

The full simulator regression passed4918 tests with16 skips before the final
conservative refinement guards. Final mandatory and changed regressions pass
384 tests; the real Chrome workflow passes on the finished assets. Chrome
uses shipped assets and mocked APIs, including XSS-safe goals, independently
assigned Cab channels, selected feedback scenes, new-design reset and consent.
The hardware pass was native readback, not a new independent Axe-Edit comparison
or an audible reproduction/loudness test. Further effect/model measurements
and owner listening remain separate work.
