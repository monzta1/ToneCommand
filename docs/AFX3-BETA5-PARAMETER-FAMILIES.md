# Beta5 parameter-family measurements

28 October 2026. This is evidence for a closed developer fixture, not a
normal planner/SEND capability or a general Beta5 write profile. The supported
firmware registry, production output gates and FM9 never-brick guard are
unchanged. Earlier accepted firmware evidence remains retained separately.

## Amp 1, channel A

Exact observed MK2 build: `33.00-beta5.20261026`, full response SHA-256
`15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616`.
Axe-Edit III1.15.02 independently identified the connected MK2. The owner
confirmed external mute and access. Only disposable preset327/scene1 was used.
The fixture contains one isolated Amp1/A at row1/column1, 59 Bassguy Bright,
with no Input, Output, cables, shunts or assigned modifiers. No Store, global
change, NAM/IR operation or change to reference326/328 was performed.

| Control | Parameter ID | Captured/native target | Separately restored value |
|---|---:|---:|---:|
| Treble Gain |1 |4.6 |5.0 |
| Bass |2 |4.7 |5.0 |
| Mid |3 |5.6 |5.0 |
| Treble |4 |4.8 |5.0 |
| Presence |20 |4.9 |5.0 |
| Master Volume |5 |4.7 |10.0 |
| Depth |16 |1.1 |0.0 |
| Level, dB |21 |-13.0 |-12.0 |

All sixteen literal operations were first observed as outgoing editor frames.
The passive observer captured no incoming buffers; it is not readback evidence.
Independent native display queries and complete bulk reads supplied readback.
The seven knob pairs use subcommand09 with the display value rounded to
float32 before division by10. The quiet Level pair uses direct dB. Depth zero
is the actual captured09 literal, not a guessed zero-as-GET substitution.
These samples do not establish arbitrary values, models or channels.

Each native SET had a fresh exact identity, current preset/scene, all eight
scene names, full grid/status, Amp/controller bulks and all32 complete25-word
modifier records. After settling/repeated reads, only the addressed Amp word
and independent display could differ. All other Amp channels and observed
state were preserved exactly. Fresh Axe-Edit instances independently displayed
the seven changed knobs and their restored values; a separate quiet Level
change/restoration received the same treatment. The final complete native
baseline was restored and a final editor check showed the original knobs
and -12dB level. Exactly16 native parameter SETs were sent, without retries.

The production adapter correctly refused a preliminary attempt before output.
That refusal is retained, not counted as a successful or uncertain write.
The successful experiment used a separate private exact-literal output probe
under the unchanged shared SysEx guard, not a profile override or production
guard relaxation. Other preliminary inspection/schema refusals also sent no
parameter SET. Private captures, state dumps and screenshots remain local.

## All336 model selector literals

The independent editor scan subsequently selected every model in the current
336-name catalog, in the recorded order1..335 followed by0. Two interrupted
sessions were retained and continued only after desktop access returned. Every
chosen model was checked against the editor's displayed name. Passive capture
contains outgoing editor traffic only, not device readback.

A separate native closed-literal probe validated all336 captured selector
frames before opening MIDI. It sent exactly336 model SETs, each once, with
Amp1/A bypassed and disconnected on327. Fresh identity and full-state checks
preceded each SET. Independent level queries and settled, repeated bulk reads
followed it. Model reset changes were confined to the addressed A-channel
words; every other Amp channel, grid/status, complete modifier record,
controller bulk and scene name stayed unchanged. Level remained -12dB. The
last model0 observation exactly matched the complete baseline, and ports
closed normally. No Store, other preset, global or shared-memory write occurred.

The final fresh post-native Axe-Edit comparison subsequently passed after
desktop access returned. A complete native comparison also matched the full
model0 baseline. A stale Gain5.0 test expectation belonged to the earlier
parameter fixture, not this model-scan baseline, whose actual Gain is4.4.
No corrective write hid that test mistake. This is completed native/editor
literal evidence, not completed model-family app acceptance. Neither
the normal Beta5 writer nor MK1/Turbo selector support is enabled by this scan.

The shared reviewed-edit API also received native negative acceptance on
this build: disabled-by-default preparation sent nothing, while explicit
opt-in rejected the unmatched firmware using GETs only. Complete before/after
state matched. This confirms refusal, not a successful parameter write.

A subsequent [separate Gain/Mid experiment](AXEFX3-BETA5-REVIEWED-AMP.md) has
its own exact Beta5 pin, model0 scope and registered native API/boundary
evidence. It does not change the older writer or approve general Beta5
parameters/models/rig building. Default connections stay read-only.

## Legacy CAB selector continuation, 30 October 2026

Fresh power/mute/desktop checks found327 genuinely empty after the restart;
the old unsaved fixture was not assumed or silently replayed. Axe-Edit placed
an isolated Amp1/A and, after the separate reviewed-Amp acceptance, Cab1/A.
No Input/Output blocks, cables or shunts were added. Amp stayed bypassed at
-12dB. A new complete, repeated native baseline was captured before CAB SETs.

On Legacy Cab1/channel A, all four Factory1 IR selectors were independently
set from displayed index1 to2, then separately restored from2 to1. These are
wire ordinals0/1 at parameter IDs4..7, not stereo LEFT/RIGHT pan controls.
Exactly eight already captured editor literals were sent once each. Every
step required fresh exact identity/context and settled, repeated full-state
readback. Only its addressed CAB word changed; all other CAB channel words,
Amp/controller bulks, complete modifier records, grid/status and names stayed
exact. No IR data was installed, overwritten or automatically unmuted.

Fresh Axe-Edit1.15.02 instances independently showed all four Factory1 slots
as index1 /1x4 Pig57 before, index2 /1x4 Pig121 after the target SETs, and
index1 /1x4 Pig57 after restoration. A final separate native comparison
exactly matched the new baseline. This closes the previously interrupted
editor comparison using fresh evidence. It establishes only these eight
literal operations, not arbitrary banks/indices, DynaCab, FullRes, other
channels, a production CAB writer or MK1/Turbo support. No Store occurred;
the disconnected two-block fixture remains unsaved on327.

## What remains before normal app support

Review and implement a bounded family-specific component with software refusal,
single-use review, expiry and uncertainty tests. Run that exact implementation
on the native device and independently compare it with the editor. Repeat for
the required model/channel, CAB, routing, scene, controller, other-effect,
timing/zero, NAM and Store operations. Then exercise the registered normal
REVIEW/CONFIRM/SEND flow on the exact candidate. These closed measurements do
not authorize model resets, full musical rigs or MK1/Turbo parity.

No audible test was performed. External mute and reduced levels are not a
physical limiter or an acoustic-feedback guarantee. Player listening and
pedal tests remain separate acceptance steps.
