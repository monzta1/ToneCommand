# Remaining acceptance work

This list separates missing implementation, unmeasured writes and intentional
safety boundaries. It is not permission to disable a gate. Evidence comes from
the maintained integration checkout, exact FW33 beta20261006 and MK2. Presets
326/328 remain reference targets; this continuation writes only322 and does not
Store. The owner's external audio remains muted.

## After the current autonomous build

| Area | Remaining requirement |
|---|---|
| Scene counts | Prefix1..8 normal SEND/full-state checks and independent post-batch eight-scene editor acceptance pass. Empty-grid-per-count and arbitrary-routing acceptance remain separate. Four Amp/Cab voices remain A-D, not eight independent channels. |
| Compressor and Graphic EQ | Modern VCA and10 Band Variable Q A-D pass actual selected-AI536-action normal SEND and independent16-effect/eight-scene editor acceptance. Other compressor/EQ modes and PEQ2 numeric voicing remain unmeasured. |
| Drive | T808 Mod is the released numeric voice. Other87-model selector captures do not prove each model's numeric domains. Re-measure model-specific controls before expanding normal voicing. |
| Other effects | Reverb, Wah, Pitch, Filter, Enhancer, Flanger and the other families need normal FW33 parameter/model integration and independent native/editor acceptance. Existing bypassed reserve blocks are not full support. |
| Extra instances | Verify second/fourth instances, complete layouts and independent preservation per family. Instance1 proof is not permission to offset an address. |
| Free routing | Promote the read-only graph diff and literal developer captures into a reviewed, state-bound planner/executor. Verify insertion, movement, removal, shunts, horizontal/diagonal/parallel cables and unrelated-scene preservation. The current normal builder uses its measured fixed row1 route only. |
| Send/Return and loops | Separate route analysis, muted native tests and stability evidence are required. Loop-family restrictions remain intentional; no feedback-safety claim follows from a single feedback percentage. |
| Controllers | Capture and replay FW33 modifier allocation/source/range/Auto Engage while preserving the complete modifier table. Physical pedal tests remain separate. Global CC mappings remain user-owned. |
| Exact zero and tempo | Seven core Amp knobs and four measured Delay/Chorus scalar zeros now pass native/normal SEND/editor acceptance. Automatic verified NONE is available within reviewed AMP/CAB timing only. Other enum/zero setters, arbitrary sync divisions and other routes need separate evidence. Numeric zero, model ordinal zero and enum zero are not interchangeable. |
| Existing presets | General third-party adoption, arbitrary routing and minimal live patches remain unimplemented. Current refinement uses a TC-created verified design and controlled full reapplication with fresh consent and protected untargeted scene settings. |
| NAM | Extend the narrow one-scene foundation/two-scene existing route to four NAM channels, multiple captures, broader effect/cab combinations and supported format coverage. A2 install/select and256-slot inventory are not universal NAM compatibility. MK1 memory needs its own device acceptance. |
| Audio | Local descriptive file comparison is not guitar isolation, aligned unit-output recording, delay estimation or automatic tonal optimization. These require new implementation and suitable reference recordings. Final musical quality still needs listening. |
| FullRes/Dyna-Cab | FullRes metadata and IR3/4 restrictions do not prove an occupied FullRes model's audible operation. Dyna-Cab mode/position controls need their own evidence. No shared IR-memory upload is authorized by name import. |
| Save As/recovery | Current Store is separately consented for the current allowlisted slot. General destination-changing Save As, opaque preset import and automatic rollback are not implemented/authorized. Unknown write outcomes must not trigger a retry or reload. |
| Runtime/device coverage | MK1, other firmware, other operating systems, Python runtimes and MIDI backends require independent acceptance. The native write path remains the measured Windows/Python3.12/mido profile. |
| Distribution | Repeat clean checkout/install against the final exact tree. Another machine/platform, remote CI and PR review are still separate. No push or publication occurs in this task. |

## Needed access and evidence

Independent Axe-Edit checks require an accessible Windows desktop, not merely
a running MIDI device. Foreground0 and failed screenshots mean the interactive
session is unavailable. Never bypass Windows session security. Offline tests,
code work and already authorized native readback can continue; affected release
flags remain disabled until the independent comparison is actually completed.

## Boundaries that should remain

Fresh target/mute consent, allowlisted storage, stop-on-mismatch, complete
readback and no automatic retry protect the workflow. They are not unfinished
features to remove. Static level/feedback limits are not an audio limiter and
cannot guarantee physical loudness, acoustic feedback prevention or equipment
safety. Broadening support means proving additional operations, not erasing
these checks.
