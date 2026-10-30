# One Axe-Fx III implementation

30 October 2026. MK1 and MK2 use the same control family, planner, protocol
implementation and effect definitions. There is no second MK1 application or
duplicate set of effect encoders. Firmware-operation acceptance is separate
from declared chassis storage capacity.

## Central chassis facts

`devices/axefx3/chassis.py` is the shared source for declared preset capacity
and persistent-memory differences. Both the shared read-only protocol and
the full workspace consume it. The declaration is not automatic detection.

| Declared chassis | Presets | User2 on NAM-era firmware | Persistent FullRes User3 |
|---|---:|---|---:|
|MK1 |512 |Reserved for NAM |None; temporary Scratchpad is not User3 |
|MK2 |1024 |Retained for IRs |64 |

The existing read-only Turbo capacity remains1024; this refactor grants no
Turbo write approval. An unknown declaration keeps conservative512-name
capacity, no persistent FullRes and no NAM-era User2 metadata. Invalid
declarations refuse rather than silently becoming MK2.

The [owner's manual](https://www.fractalaudio.com/downloads/manuals/axe-fx-3/Axe-Fx-III-Owners-Manual.pdf)
documents preset capacities. The
[Blocks Guide](https://www.fractalaudio.com/downloads/manuals/fas-guides/Fractal-Audio-Blocks-Guide.pdf)
documents the MK2 FullRes bank. NAM addressing and installation approval
remain separately tracked in the existing hardware evidence.

## Correct cabinet metadata, without IR writes

Known October6 FW33 and October26 Beta5 builds use the same modern user-name
layout: User1 and User2 have1024 entries, with separate64-entry FullRes User3.
This is a local name-list schema, not a selector or firmware-write alias.
Unknown firmware does not acquire this schema or a writable profile.

Previously Beta5 fell through to the old name layout: User1 slot1024 could
be rejected and User2 names could be mapped using the old combined-bank
address. The shared schema now keeps the banks distinct. Switching to MK1
preserves the upper half of User1 and removes only local names for reserved
User2 and unsupported persistent FullRes. It does not delete device contents.
Invalid mixed imports fail atomically, preserving existing local names.

Private name caches stay separate per exact firmware and chassis. Beta5 never
inherits the October6 cache; MK1 never imports MK2's bank permissions. Validly
checksummed but reserved cache entries are still rejected. These caches contain
names only, not IR data, NAM weights, account tokens or proof of audible IRs.

## Evidence and next stage

Offline tests compare both chassis' complete parameter specifications and
sample exact encoded frames, storage boundaries, normal profile/import API,
cache isolation and refusal paths. These are software parity tests, not a
physical MK1 regression. A native GET-only MK2 full-state comparison also
confirmed that this change did not alter the current preset state.

No firmware fingerprint, writable-family gate, MK1 writer approval, model
selector, memory allowlist or FM9 never-brick guard is broadened. Existing
MK2-only proof gates remain visible rather than being removed as if a local
chassis choice were hardware evidence. New shared operations should consume
one implementation and receive explicit evidence for the intended scope.

Next release work is the same for both chassis: complete the shared reviewed
AMP/CAB workflow, then effects/controllers/scenes, refinement and storage.
NAM/IR installation and MK1 storage need their own separate acceptance. This
foundation is not a declaration that the full Beta5 preset builder is ready.

## Bounded Beta5 AMP/CAB experiment

`TONECOMMAND_BETA5_CORE=1` enables a separate, exact-identity experiment in
the existing `/axefx3` workspace. It does not add Beta5 to the legacy registry's
writable firmware list. Unknown builds, an undeclared chassis, another grid,
active or assigned modifiers, missing reads and changed targets refuse.

The common implementation supports one scene on channel A with exactly
`Input 1 -> Amp 1 -> Cab 1 -> Output 1` in the first four cells of row1.
It can construct this route on an empty grid or configure the same existing
route. It never clears a different preset or resumes a partially failed build.
The AI proposes an exact catalog amp, IR1 cabinet and eight amp settings.
The server, not the AI, creates the staging and routing operations.

The normal request, clarification, review, confirmation and SEND interface is
used. Both target confirmation and external mute remain required. Reviews are
device/state/catalog-bound, expire after ten minutes and are single-use.
Transport uncertainty consumes the review and locks this connection until
reconnect and inspection. There is no automatic retry, rollback or Undo.

The output is staged at -18 dB and the amp at -18 dB before voicing. The amp
final level is restricted to -60..-12 dB. IR1 is explicitly mixed at0dB,
center; IR2-4 are explicitly muted. Slot-level and block-level encodings are
separate. These are conservative policies, not a physical audio limiter.
External muting must continue throughout all channel/model transitions.

Only bank selection changes, never IR data. MK1 cannot select NAM-reserved
User2; MK2 may select that bank if current nonempty local metadata exists.
This core has no Dyna-Cab, FullRes, NAM, controller, extra-effect, multiple-scene,
refinement or permanent Store operation. Unsupported requirements must not
be presented as a complete build. The musical AI can ask about reduced scope;
unsupported structured selections refuse before planning.

### Functional acceptance on 30 October

Measured device: MK2, exact `33.00-beta5.20261026`, Axe-Edit III1.15.02.
All work used unsaved preset327 with external audio muted. Presets326 and328,
resource memory, global controls and firmware were not changed.

- CAB bank/index boundaries and Amp knob/level endpoints were captured in the
  editor, replayed natively once per operation, read back repeatedly and checked
  for preservation of unrelated complete block/channel/controller/modifier state.
- Native construction by the new component passed from an independently
  editor-confirmed empty grid, including all three actual cables.
- Actual Chrome, the selected AI backend, review, both acknowledgements and
  exactly one normal SEND passed on the resulting existing core route. The AI
  selected Brit 800 2204 High and Factory2 slot517,4x12 Brit70s GB57B.
- Fresh independent Axe-Edit comparisons confirmed the final model, eight amp
  controls, cabinet, visible mute states, output level, names and connected grid.
  This editor's UIA M-button labels incorrectly all report Off; screenshots and
  native mute-word readback were used instead of treating those labels as proof.

These are functional MK2 results, not a listening test, tone-match score,
physical loudness measurement, MK1 hardware acceptance or approval of every
possible model/IR combination. MK1 consumes the same code and has separate
storage restrictions, not a second application or automatic evidence alias.
Private timestamped traces and source-hash reports remain local, not in release
packages. Broader effects, multi-scene construction and storage remain next work.
