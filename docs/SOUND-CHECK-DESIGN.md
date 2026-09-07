# ToneCommand Sound Check and Guided Correction Design

Status: implementation-ready design, gated by hardware feasibility work  
Updated: 2026-09-07  
Related specification: `../../ir-command/docs/PRODUCT-DESIGN-V2.md`
Experience north star: `NEXT-LEVEL-PRODUCT-DESIGN.md`

## 1. Product promise

ToneCommand should not stop at setting parameters that ought to produce the
requested sound. It should be able to replay a known guitar input through the
FM9, measure the result, identify objective misses, propose the smallest safe
correction, and prove whether the approved correction helped.

The player-facing capability is called **Sound Check**. Terms such as FFT,
LUFS, correlation, CoreAudio, channel routing, and re-amping belong in
expandable evidence or diagnostics, not the primary workflow.

The closed loop is:

`PLAY KNOWN INPUT -> CAPTURE -> VALIDATE -> MEASURE -> EXPLAIN -> PROPOSE`

If the player accepts a correction, it uses the product's existing loop:

`PLAN -> REVIEW -> CONFIRM -> SEND -> READ BACK -> RE-MEASURE`

The differentiator is not a graph. It is a trustworthy answer to:

> Did the FM9 actually produce the result we agreed on, and did the fix make it
> measurably closer without changing anything else?

## 2. Product boundaries

Sound Check can establish objective and relative facts about the FM9's recorded
USB output. It cannot decide whether a tone is inspiring, musical, authentic,
or enjoyable.

### 2.1 What it may claim

- the processed return exists and whether the captured FM9 USB endpoint reached
  or exceeded a calibrated headroom threshold;
- the same input made one scene louder or quieter than another;
- a scene is brighter, darker, fuller, thinner, wider, or noisier than a named
  baseline using disclosed metrics;
- a lead is a measured number of loudness units above a rhythm baseline;
- a stereo result has a disclosed mid/side ratio, correlation, and mono
  fold-down loss;
- an approved correction moved the measurement toward or away from its target;
- repeated captures were or were not stable enough to trust.

### 2.2 What it may not claim

- `sounds good` or `sounds professional`;
- an artist's exact tone from frequency balance alone;
- amp feel, sag, pick response, or nonlinear character from a spectrum only;
- noise-gate performance from injected digital silence;
- full-rig audience sound when it measured the FM9 USB output;
- reliable scene comparison from different human performances;
- a passed check when required information was absent;
- a tone clone from a mastered song containing other instruments.

## 3. Corrections to the original concept

### 3.1 A controlled stimulus is mandatory for correction

Arbitrary playing changes pick force, note choice, chord density, pickup noise,
timing, and muting. LUFS, spectrum, and crest factor from different performances
are not comparable enough to drive parameter changes.

Sound Check has two internal protocols:

| Protocol | Input | Valid use |
|---|---|---|
| Controlled | The exact same DI clip re-amped through every scene | Scene comparison, correction, regression, reference balance |
| Live | The player performs while ToneCommand listens | Informative feedback about that performance and analog noise |

The UI does not ask the player to choose a technical mode. It routes by intent
and data availability. A correction requires Controlled. A live performance can
produce observations, never an automatic numeric fix.

### 3.2 The recording backend is missing from the original dependency plan

`soundfile` reads and writes audio files. It does not capture a USB audio
device. The implementation needs an injected audio transport, with a production
backend such as `python-sounddevice` over PortAudio and a deterministic test
backend.

### 3.3 FM9 re-amp routing is a hard feasibility gate

The official FM9 manual documents fixed 48 kHz, 8-in/8-out USB audio. Its re-amp
flow sends the DI to computer output 5, routes USB 5/6 into an FM9 input, and
records the processed result from computer inputs 1/2. The documented flow also
changes global Input 1 routing to DIGITAL and requires restoring it to ANALOG.

ToneCommand does not currently have a proven, safe global-I/O read, write, and
restore path. The simulator models MIDI state, not USB audio. No production
measurement work should begin until a hardware spike proves:

- audio and MIDI can coexist in the existing single-server process;
- the exact computer channel mapping on macOS and Windows;
- a processed return can be distinguished from dry playback or loopback;
- current global routing can be read reliably;
- temporary routing can be applied without touching flash;
- routing returns to its exact starting state after success, error, cancel,
  disconnect, and process restart;
- the user's monitors cannot enter a feedback loop or receive an unsafe level.

If those facts cannot be proven, the first release must guide the player
through the official manual routing and verify the returned signal. It must not
silently change global I/O.

### 3.4 Generic tone thresholds are contextual heuristics

Energy above 8 kHz is not inherently fizz. Stereo width is not inherently
better. A clean does not universally require chorus, delay, and reverb. The
correct target depends on role, request, guitar, pickup, tuning, arrangement,
reference, and player preference.

Rules must be separated into six classes:

| Class | Example | Enforcement |
|---|---|---|
| Hardware safety | No unapproved flash write | Hard block |
| Acquisition validity | Missing frames, wrong route, dropout, or file truncation | Invalid measurement |
| Signal concern | Low USB endpoint headroom or unexpected silence | Finding, not automatically invalid |
| Device correctness | Unsupported action or incompatible format | Hard block |
| Intent target | Lead requested 2 to 3 LU above rhythm | Compare to explicit request/baseline |
| Style or preference | 1980s clean is usually lush | Recommendation, never universal pass/fail |

The prose in `config/tone_rules.md` currently mixes these classes and contains
conflicting numeric guidance. Sound Check must consume a structured, versioned
policy document. It must not parse prose into enforcement.

### 3.5 Empty findings are not a pass

The current deterministic review builds a summary from plan deltas. Parameters
not present in the delta are unknown. An empty findings array can therefore
mean `no problem`, `no coverage`, or `could not infer scene roles`.

Every checker must return:

- status: `verified`, `concern`, `unknown`, `invalid`, or `not_applicable`;
- coverage: which scenes, metrics, and parameters were observed;
- evidence: source and repeatability;
- missing facts;
- findings.

Player copy may say `No issues found in the 4 checks I could run`. It may not say
`gig-ready` when zero checks had enough information.

### 3.6 A browser edit invalidates prior review evidence

Review currently allows editable numeric values. Those edits mutate the browser
plan after the server created plan-time validation and tone-review findings.
Range validation runs again during apply, but the Confirm view can still show
stale tone guidance.

The future contract must send every edit back through server-side validation,
dependency analysis, policy evaluation, and plan digesting before Confirm can
be enabled. A changed plan gets a new immutable revision and invalidates the old
confirmation.

### 3.7 Rename tone matching

The feature is **frequency-balance matching**. For a full mastered mix it is a
broad estimate only. Prefer an isolated guitar track or a reference produced by
re-amping the same DI. Never claim that an EQ curve recreates nonlinear amp
behavior, dynamics, production, or playing feel.

### 3.8 Recovery is a prerequisite, not a best effort

The current apply path can continue after an undo snapshot fails. That is not
acceptable for measurement-guided correction. A Sound Check correction may not
send unless a complete recovery snapshot exists and can be validated. The only
exception would be an action with a separately proven atomic inverse, and no
such exception is assumed in v1.

### 3.9 Current implementation audit

The existing planner and tone review are useful foundations, but several
current behaviors would make a measured result look more certain than it is:

- `fm9/tone_review.py` reviews only values present in a plan delta and skips
  unknown roles and values.
- `ui/index.html` currently renders an empty finding list as a successful tone
  check even when coverage was zero.
- editable Review values mutate the browser action object without re-running
  server tone review, semantic validation, or blast-radius calculation.
- `/api/apply` receives the mutable client action list. It checks individual
  actions and preset number, but does not require the immutable plan revision
  and complete semantic state that were reviewed.
- apply can continue after an undo snapshot attempt fails.
- `config/tone_rules.md` says clean amp level should be roughly +15 to +18 in
  one section and near 0 or positive in another.
- current guidance alternates between amp level and `OUTPUT_SCENEn` as the
  scene-balancing lever without a calibrated decision rule.
- there is no audio transport or measurement-session state machine.
- fields related to global input source appear in the catalog, but the registry
  and device layer expose no hardware-verified routing transaction.

These issues do not mean the current Send path is generally unsafe. They mean
Sound Check must first strengthen the reviewed-plan contract and evidence model
instead of attaching DSP to the existing optimistic status display.

## 4. Five-second player experience

Sound Check is contextual to Send, not a sixth workflow tab. When the Tone Goal
contains measurable acceptance criteria and preflight is ready, Confirm may
offer `SEND AND CHECK` for that exact bounded transaction. Otherwise it appears
after Send as a calm next action:

```text
SENT AND VERIFIED
18 changes reached the FM9 and read back correctly.

[CHECK THE SOUND]
```

After a successful check, show one primary outcome:

```text
SOUND CHECK
Scene 2 is 5.8 LU quieter than your rhythm baseline.
The result repeated within 0.2 LU.

[REVIEW BALANCE FIX]                 [SEE 3 OTHER CHECKS]
```

If everything measured is within the agreed target:

```text
SOUND CHECK
Balance verified across 6 scenes. No silence or USB headroom concern detected.
Stereo and tonal checks are available in details.

[KEEP THIS VERSION]
```

If the capture is not trustworthy:

```text
I could not get a stable reading from Scene 4.
Play it again, or keep the tone as it is. Nothing was changed.
```

No raw device error, endpoint, timeout, buffer, or channel number appears in the
primary message.

## 5. Player journeys

### 5.1 One-time Guitar Card

The best controlled source is the player's own guitar, pickup, tuning, and pick
attack. The player sees a Guitar Card rather than a laboratory calibration
screen:

```text
SEVEN STRING
Drop C | Bridge humbucker
Ready for Sound Check
```

On first use:

1. ToneCommand asks for 15 to 25 seconds of playing.
2. Five musical cues request `CHUG`, `RING`, `LEAD`, `CLEAN`, and `REST`.
3. The FM9 records the raw Instrument DI from USB input 5 while the player hears
   the current processed tone.
4. Each cue lights when it contains enough valid, useful material. Only an
   inadequate cue is repeated.
5. The DI is stored locally with a guitar profile such as `Drop C bridge
   humbucker`.
6. The player can rename, replace, export, or delete it.

Each cue stores exact time regions and a coverage manifest. Metrics may use only
regions with adequate excitation. A band without useful source energy produces
`unknown`, not an apparently precise tonal conclusion.

A bundled, properly licensed generic DI may be offered for immediate testing,
but the UI says whose guitar and tuning it represents. Generic and personal DI
results do not share baselines.

### 5.2 Check a newly sent preset

1. The player chooses `SEND AND CHECK`, or Send completes with successful
   parameter read-back and the player chooses `CHECK THE SOUND`.
2. The consent is limited to the exact named send and measurement transaction.
3. ToneCommand detects the relevant scenes, matching Guitar Card, and useful
   riff cues.
4. Before measurement begins, Review names the bounded transaction: preset edit
   buffer, scenes, source clip, temporary routing, capture destination, and
   restore.
5. A post-Send check receives one confirmation. `SEND AND CHECK` uses the exact
   confirmation already given and never asks again for the same scope.
6. ToneCommand runs one conditioning pass, two measured passes, and a bounded
   third pass only when metric-specific agreement requires it.
7. It restores global routing before analyzing or presenting results.
8. Capture validation runs before musical metrics.
9. The UI shows one primary finding and a compact coverage summary.

### 5.3 Approve a correction

1. `REVIEW BALANCE FIX` creates a normal plan revision.
2. Review shows exact parameter delta, affected scenes, expected metric move,
   confidence, and restore point.
3. Confirm binds the device, preset digest, plan digest, source clip, and target.
4. Send snapshots, applies, reads back, and captures again.
5. The result compares Original, Previous, and Current measurements.
6. If the measurable target improved, ToneCommand labels it `Closer to target`
   and asks the player to compare.
7. It becomes Last-known-good for that exact context only when the player
   explicitly keeps it.
8. If worse, ToneCommand stops and offers Original or Last-known-good.

### 5.4 Live observation

For `listen while I play`:

- show a short countdown and record one performance;
- include pickup noise and analog gate behavior;
- report capture truncation, low USB endpoint headroom, silence, broad balance,
  and instability;
- label the result `this performance`, not a reusable baseline;
- do not calculate a numeric scene correction unless the same captured DI is
  subsequently re-amped through the compared scenes.

## 6. Architecture

```text
UI
  request / bounded consent / one finding / evidence / recovery
                         |
                         v
SoundCheckService
  orchestration / state machine / manifests / result comparison
       |                  |                    |
       v                  v                    v
AudioTransport       MeasurementEngine     FixPlanner
production + sim     validity + metrics    levers + blast radius
       |                                       |
       v                                       v
HardwareSession ----------------------> existing Plan safety path
MIDI lock + audio + snapshot + restore  Review / Confirm / Send / read-back
```

### 6.1 Required modules

`fm9/audio_transport.py`

- interface for device discovery, channel enumeration, playback, capture,
  cancellation, and dropout reporting;
- no planner or FM9 protocol knowledge;
- `SoundDeviceTransport` and `SimAudioTransport` implementations.

`fm9/measurement_session.py`

- explicit state machine;
- preflight, snapshot, temporary route, capture, restore, validate, analyze;
- persistent recovery journal;
- owns no flash-write primitive.

`fm9/audio_validation.py`

- sample-rate, channels, duration, signal, route identity, acquisition
  integrity, endpoint headroom, dropout, synchronization, SNR, and
  repeatability gates.

`fm9/audio_metrics.py`

- loudness, band balance, dynamics, stereo, noise, tail, technical defects;
- pure functions over arrays plus a measurement manifest.

`fm9/sound_policy.py`

- structured rule and target loading;
- scope, class, source, confidence, and version;
- evaluates metrics without touching hardware.

`fm9/fix_planner.py`

- maps a valid finding to candidate FM9 levers;
- reads the current graph and channel/scene sharing;
- returns a proposed action list with predicted effects and confidence;
- never calls `run_action`.

`fm9/tone_receipt.py`

- immutable request, plan, hardware, measurement, and restore evidence;
- printable/exportable player record.

Server routes should live in a focused router rather than adding more global
state to `server.py`.

### 6.2 Immutable PlanArtifact

Review, Confirm, and Send must share one server-held object:

```json
{
  "plan_id": "uuid",
  "revision": 4,
  "actions_digest": "sha256",
  "target_preset": 133,
  "target_state_digest": "sha256",
  "validated_actions": [],
  "blast_radius": {},
  "policy_result": {},
  "measurement_provenance": {},
  "confirmed_at": null
}
```

A Review edit creates a new revision on the server, re-runs action validation,
blast-radius analysis, structured policy checks, and confirmation facts, then
returns the revision. Confirm seals that exact revision. Send accepts only
`plan_id` and `revision`, never a replacement action list from the browser.

Any edit, preset change, relevant front-panel change, device reconnect, or
measurement invalidation disarms confirmation. The semantic state digest covers
the values and topology the plan depends on, not only the preset number.

## 7. Measurement session state machine

```text
CREATED
  -> PREFLIGHT
  -> CONSENTED
  -> SNAPSHOTTED
  -> ROUTED
  -> CAPTURING
  -> RESTORING
  -> RESTORED
  -> VALIDATING
  -> MEASURING
  -> COMPLETE
```

Any error, cancel, disconnect, or process shutdown after `SNAPSHOTTED` enters:

```text
RESTORING -> RESTORED -> ABORTED
```

If restore cannot be verified:

```text
RECOVERY_REQUIRED
```

No result is shown as reliable before `RESTORED`. Analysis may run only after
hardware state is safe again. A startup recovery check runs before new hardware
work and resolves any incomplete journal.

### 7.1 Transaction rules

- One ToneCommand process owns MIDI and audio device work.
- The hardware lock order is documented and invariant.
- Snapshot edit-buffer identity, preset number/name, current scene, tempo,
  relevant global I/O, controller and modifier positions, and all temporary
  destinations.
- All temporary changes are exact, bounded, and shown before the one session
  confirmation.
- No STORE action is available to Sound Check.
- Re-check device and preset digests immediately before routing and each send.
- A disconnect halts the transaction. Reconnect triggers read and reconcile,
  never continuation from an assumed step.
- Routing restore uses `finally` plus the persistent recovery journal.
- Restore is read back. A sent restore command is not proof of restoration.
- A panic action cancels playback first, lowers software output to silence,
  then begins restore.

### 7.2 Audio safety envelope

The safety envelope is owned by the server process and remains active when the
browser closes or disconnects:

- validate the destination device and channel map before any non-silent frame;
- bind replay level to a valid device-specific calibration record;
- cap replay below a hardware-tested maximum;
- ramp playback in and out to prevent abrupt full-scale starts and stops;
- detect and block software-monitoring and feedback-loop configurations;
- keep a watchdog independent of browser state;
- give one transaction exclusive playback and capture ownership;
- cancellation silences playback before any routing or scene restore;
- reconnect never resumes playback automatically;
- loss of route identity or device identity immediately aborts to recovery.

The player always has a visible and keyboard-accessible `STOP AUDIO` control.
The server treats browser disappearance as a stop request, not permission to
continue unattended.

## 8. Measurement manifest

Every capture has enough context to reproduce or invalidate it:

```json
{
  "schema_version": 1,
  "session_id": "uuid",
  "device": {
    "adapter": "fractal-fm9",
    "firmware": "11.00",
    "device_identity": "local-hash"
  },
  "preset": {
    "number": 133,
    "name": "Modern Drop C",
    "edit_buffer_digest": "sha256"
  },
  "scene": 2,
  "performance_controls": {
    "expression_positions": {},
    "modifier_state_digest": "sha256"
  },
  "source": {
    "di_id": "di_...",
    "sha256": "...",
    "guitar_profile": "Drop C bridge humbucker",
    "coverage_manifest": "coverage_..."
  },
  "measurement_boundary": "fm9_usb_processed",
  "reamp_calibration_id": "cal_...",
  "audio": {
    "device_name": "FM9",
    "sample_rate_hz": 48000,
    "playback_channels": [5],
    "capture_channels": [1, 2],
    "frames": 960000
  },
  "routing_before": "digest",
  "routing_during": "digest",
  "routing_after": "digest",
  "metric_version": "1.0.0",
  "policy_version": "1.0.0",
  "created_at": "ISO-8601"
}
```

The UI says `Measured at the FM9 USB output`. It never implies the room, PA,
front-of-house processing, or audience position was measured.

### 8.1 Measurement boundary

Every capture and every derived claim declares exactly one boundary:

| Boundary | What it includes | Initial support |
|---|---|---|
| `fm9_usb_processed` | Digital processed return from the FM9 | Version 1 after hardware proof |
| `fm9_analog_output_loopback` | Physical FM9 output and an external input path | Future separate calibration |
| `monitor_or_room_microphone` | Monitor, room, placement, and microphone | Future separate product surface |

Evidence from one boundary never inherits claims from another. A USB result
does not verify the analog outputs, cabling, PA, monitors, room, or audience
position.

### 8.2 Re-amp calibration record

Replay level is part of the stimulus and cannot be a generic constant. Changing
it can change gain, compression, gate action, and nonlinear response. A valid
calibration binds:

- FM9 or connection identity and firmware;
- Guitar Card and source DI hash;
- operating system, USB driver, device, and channel map;
- relevant global input and output state;
- original DI capture level;
- replay gain and measured round-trip level;
- monitoring safety cap;
- creation time and explicit invalidation reasons.

ToneCommand must not automatically lower the replay stimulus merely because the
processed return is hot. It first distinguishes failed acquisition from a valid
measurement showing limited output headroom. Changing the stimulus creates a
new calibration and invalidates direct comparison with the prior one.

### 8.3 Claim Record

Every conclusion shown to the player derives from an immutable Claim Record:

```text
ClaimRecord
  claim_id and tone_version_id
  subject and comparator
  measurement boundary
  estimate, unit, and direction
  repeatability interval and minimum detectable change
  validity status and coverage
  source capture and asset hashes
  device, routing, and semantic state digests
  algorithm, policy, calibration, and capability versions
  supporting and contradictory evidence
  limitations and invalidation reasons
```

Identity confidence, eligibility, intent fit, preference confidence, preview
fidelity, and measurement repeatability stay separate. A Claim Record never
compresses them into one confidence percentage.

## 9. Capture validity

Validity precedes interpretation. A failed gate produces no fix.

Required gates:

- device is the expected FM9;
- exact 48 kHz stream;
- expected channel count and mapping;
- captured output aligns to the known DI within a plausible latency range;
- route identity is established using read-back, simultaneous references when
  supported, safe control intervals, latency, and correlation evidence;
- sufficient active signal and duration;
- no NaN, infinite sample, malformed frame count, dropout, or discontinuity;
- no capture-path full-scale truncation or converter acquisition failure;
- no sustained digital zero unless silence is the intended probe;
- SNR sufficient for the requested metric;
- repeated runs agree within empirically validated tolerance;
- modulation and time effects receive adequate pre-roll and tail capture.

Do not invent final thresholds in the design. Establish them using hardware
captures and a versioned validation corpus. Before calibration, a result outside
an observed stable range is `unstable`, not `failed tone`.

Expression pedals and time-varying modifiers are part of the captured state.
ToneCommand must never silently disable them. It may ask the player to park a
pedal at a named position, record the observed position, or mark the result
unstable if the position changes between passes.

Low true-peak headroom at the FM9 USB endpoint is normally a valid measured
concern, not an acquisition failure. An intentionally nonlinear guitar waveform
cannot prove that a particular internal block clipped. Sound Check reports the
observed boundary and avoids assigning an internal cause without block-level
evidence.

### 9.1 Adaptive repeatability

Use a bounded protocol rather than assuming two captures are sufficient:

1. Run one conditioning pass after selecting the preset or scene.
2. Capture two measured passes with deterministic pre-roll and tail handling.
3. Compare agreement using metric-specific tolerances.
4. Capture one additional pass when disagreement exceeds tolerance.
5. Stop at the fixed maximum and return `unstable` if the interval remains too
   wide.

Counterbalance scene order when practical to expose thermal, temporal, or
effect-state drift. Record tempo, modifier positions, scene-settle time, tail
flush policy, and ordering. Track the 95th percentile and worst-case
repeatability, not only the median.

### 9.2 Route verification

A processed waveform merely differing from the DI is not proof of the correct
route. Route identity requires the strongest available combination of:

- read-back of every observable routing field;
- simultaneous dry-reference and processed captures when supported;
- expected latency and correlation bounds;
- expected silence during a safe control interval;
- a channel identity stored in the calibration record;
- an immediate abort when evidence is contradictory or ambiguous.

If global routing cannot be read back, automated routing remains blocked. The
product guides the player through the official manual route and validates the
returned signal without claiming it controlled the route.

### 9.3 Scene protocols

Sound Check distinguishes:

- `isolated_scene`: condition the selected scene, then measure its steady
  result with controlled pre-roll and tail;
- `scene_transition`: capture a real A-to-B change including gap, transient,
  spillover, tail continuity, tempo behavior, and level discontinuity.

Time effects retain memory. The system must not clear effect state for an
isolated measurement and then claim it measured live transition behavior.

## 10. Measurement engine

### 10.1 Loudness and scene balance

Use the same DI, active-region mask, pre-roll, and tail policy for every scene.
Report gated integrated or short-term loudness plus RMS as supporting evidence.

Targets are role-relative and request-derived:

- rhythm scenes compare to the selected rhythm baseline;
- clean scenes compare to the requested relationship, usually level with the
  rhythm when that is the player's intent;
- leads compare to the requested boost, often a starting point of 2 to 3 LU;
- hard technical checks catch silence and acquisition failure, while a named
  policy may flag low endpoint headroom. Neither defines musical hierarchy.

For a pure downstream scene-output gain that has been hardware-calibrated,
measured delta may map closely to a parameter delta. Cap each proposal, protect
headroom, and verify again. Do not assume a one-to-one response until firmware
11 measurements prove it.

### 10.2 Frequency balance

Use windowed, aligned, active audio and log-frequency smoothing. Prefer band
ratios and response deltas over one spectral-centroid number.

Initial descriptive regions, to be calibrated:

- rumble: below roughly 60 Hz;
- low control: roughly 60 to 120 Hz;
- body: roughly 180 to 500 Hz;
- presence: roughly 1.5 to 4 kHz;
- upper bite and fizz potential: roughly 6 to 10 kHz;
- air/noise: above roughly 10 kHz.

These regions describe evidence. They are not universal pass bands. A finding
must name its baseline, such as `2.4 dB more 6 to 10 kHz energy than your saved
rhythm reference`.

### 10.3 Dynamics

Use crest factor, short-term loudness distribution, and transient retention.
For nonlinear behavior, use the same DI at several controlled input levels and
observe the output gain curve. This is more meaningful than declaring amp feel
from one crest-factor reading.

Do not report Loudness Range from a short calibration riff. EBU guidance does
not recommend LRA for short-form material of this duration. Use repeatable
short-term measures and the controlled input-output envelope instead.

### 10.4 Stereo

Measure:

- mid/side energy ratio;
- L/R correlation;
- inter-channel level and delay;
- mono fold-down level loss and spectral cancellation.

`Wider` is not automatically better. A stereo lead that loses important body in
mono is a concern even if its correlation looks wide.

### 10.5 Noise and gate

Digital zero does not reproduce pickup, cable, electromagnetic, or preamp noise.
Gate verification uses the quiet section of a live personal DI captured through
the analog Instrument input. Record input and processed output so the result can
distinguish a quiet guitar from effective gating.

### 10.6 Delay, reverb, and dry-note integrity

Capture enough tail to measure decay and repeat timing. Compare onset energy to
late energy to catch an effectively hidden dry attack. Time-varying effects may
require multiple runs and receive a lower repeatability status.

### 10.7 Technical defects and concerns

These may produce invalid acquisition or hard findings:

- capture-path full-scale truncation, malformed samples, or missing frames;
- sustained silence where signal is expected;
- DC offset;
- dropouts, discontinuities, or channel loss;
- unintended dry loopback;
- major mono cancellation;
- incompatible sample rate or channel map.

Low USB endpoint headroom may produce a concern. The final waveform alone does
not prove unintended clipping inside an Amp, Drive, or another internal block.

## 11. Structured sound policy

Replace enforceable prose with data such as:

```yaml
schema_version: 1
rules:
  - id: acquisition.complete_frames
    class: acquisition_validity
    scope: every_capture
    metric: missing_or_truncated_frames
    comparison: equals
    target: 0
    severity: invalid
    source: capture_integrity

  - id: output.endpoint_headroom
    class: signal_concern
    scope: every_capture
    metric: true_peak_dbfs
    comparison: below
    target: player_or_context_policy
    severity: concern
    source: named_output_policy

  - id: role.lead_lift
    class: intent_target
    scope: lead_vs_rhythm
    metric: loudness_delta_lu
    range: [2.0, 3.0]
    default_only_when_request_is_silent: true
    severity: suggestion
    source: player_rulebook
```

Each rule carries:

- stable id;
- class and scope;
- metric and comparison;
- hard, request-derived, reference-derived, style, or personal target;
- provenance;
- confidence;
- applicable firmware and device profile;
- version and migration history;
- player-facing copy template;
- eligible fix levers, if any.

The markdown rulebook remains useful explanation and planner context. It is not
the execution engine.

## 12. Fix planning

```text
VALID FINDING
  -> candidate levers
  -> current parameter and topology read
  -> channel/scene dependency graph
  -> blast-radius elimination
  -> headroom and range validation
  -> smallest reversible proposal
  -> normal Plan revision
```

### 12.1 Confidence classes

| Fix class | Example | Player label |
|---|---|---|
| Direct | Calibrated per-scene output trim for a measured level gap | Direct |
| Directional | Lower cab high cut or presence for excess upper energy | Directional |
| Exploratory | Several shared parameters could explain the result | Needs audition |

Only Direct may calculate a numeric change from a measured gap, and it remains a
proposal. Directional fixes adjust one lever per pass. Exploratory findings ask
the player to audition options instead of pretending there is one answer.

### 12.2 Dependency rules

- Know which scenes share each block channel.
- Prefer per-scene controls when the finding is scene-specific.
- Show every affected scene in Review.
- Never fix whole-signal loudness by thinning wet effects unless the request is
  explicitly about wet balance.
- Do not correct darkness with a lever that creates a clipping or fizz concern.
- Re-run the whole applicable policy set after every edited plan.
- No plan may predictably violate a hard rule.
- Unknown unmeasured impact remains visible before Confirm.
- After Send, re-run every applicable hard check across affected scenes.
- If a new hard finding appears, stop and offer Last-known-good or Original.

### 12.3 Bounded convergence

- Maximum two player-approved correction passes after the baseline.
- Preserve Original, Previous, Current, and context-specific Last-known-good.
- Track direction and magnitude for every metric.
- If a pass worsens the target beyond repeatability tolerance, stop.
- If direction reverses twice or improvement falls below measurement
  resolution, stop.
- Offer restore, keep, or manual control. Never keep hunting autonomously.

### 12.4 Optional black-box sensitivity calibration

The FM9 itself can reveal which lever controls a metric on the current preset.
A future measurement plan may enumerate small reversible edit-buffer probes,
such as `presence +0.5`, capture each result, and restore after each probe. The
player confirms the complete bounded probe list once.

This produces a local sensitivity map for that exact firmware, amp model, cab,
topology, source level, state digest, and operating point. The map is valid only
inside a small declared trust region, carries uncertainty for every estimated
effect, and is invalidated by a relevant state change. It can guide a bounded
proposal but is not a digital twin. It remains edit-buffer only, read-back
verified, fully reversible, and blocked until the measurement transaction is
hardware-proven.

## 13. Reference comparison

### 13.1 Accepted reference quality

Rank references:

1. Same DI re-amped through a player-approved golden preset.
2. Isolated guitar stem with known role and minimal mastering.
3. Solo guitar excerpt with unknown processing.
4. Full mastered mix.

Only 1 supports strong correction claims. 2 and 3 support directional
frequency-balance comparison. 4 is labeled `broad estimate only` and should
usually guide intent, not generate an EQ curve.

### 13.2 Comparison controls

- align relevant active regions;
- do not compare a palm-muted riff with a sustained lead;
- match playback loudness for audition, but preserve raw measurements;
- keep source separation optional and explicitly uncertain;
- never upload copyrighted reference audio by default;
- store reference audio and features locally;
- show which parts of the reference were actually measured.

## 14. Dependencies

Keep audio support optional so the existing MIDI product retains a clean
installation.

Recommended `audio` extra:

- `numpy`: arrays, correlation, mid/side, and raw math;
- `scipy`: proven STFT, Welch spectrum, filters, correlation, and polyphase
  resampling;
- `soundfile`: robust local audio file I/O;
- `sounddevice`: PortAudio device discovery, playback, and capture;
- `pyloudnorm`: BS.1770 loudness calculation, validated against the project's
  measurement corpus before release.

`librosa` is not required for the first release. It adds substantial dependency
weight on top of operations available in SciPy. Reconsider only if a specific
validated feature materially reduces custom orchestration.

Pin compatible ranges, expose dependency health in diagnostics, and keep every
audio library behind interfaces so the no-audio product still runs.

## 15. Privacy and data handling

- Personal DI clips, live captures, references, features, and receipts stay
  local by default.
- The player explicitly chooses library locations and may revoke them.
- Support bundles exclude audio, prompts, paths, filenames, and tokens unless
  individually selected.
- Telemetry is separately opt-in and contains only coarse event categories and
  durations.
- Every stored capture has retention controls: keep, auto-delete after session,
  export, and delete now.
- Hashes used as local identities are not uploaded.
- Browser audio URLs use opaque, time-bounded handles, not local paths.

## 16. Tone Receipt

The canonical record is the Tone Version defined in the experience
specification. The Tone Receipt is its player-readable and exportable
projection, not a separate history database. After a build or correction it
answers:

- what the player requested;
- which plan revision was confirmed;
- exact changes and affected scenes;
- target device, firmware, preset, and edit-buffer digest;
- write and read-back result;
- whether anything was stored to flash;
- Calibration Riff identity and measurement location;
- capture validity and repeatability;
- metrics, baselines, and policy version;
- fix prediction versus measured result;
- Original and player-kept Last-known-good restore points;
- remaining unknowns.

This receipt is the trust artifact that turns `the app says it worked` into an
auditable chain of evidence.

## 17. Failure and recovery

| Failure | Required behavior |
|---|---|
| FM9 unavailable | Preserve request, no measurement transaction starts |
| Audio device busy | Offer retry and close the conflicting app, no protocol text |
| Wrong sample rate | Stop before playback and guide correction |
| Dry loopback captured | Mark invalid, change nothing |
| Capture path truncated | Correct acquisition gain without changing the FM9 stimulus, then re-run with approval |
| USB endpoint has low headroom | Report the valid concern, preserve the calibrated stimulus, propose nothing automatically |
| Capture unstable | Report no reliable reading, propose no fix |
| Device or preset changes after Review | Invalidate confirmation and rebuild the plan |
| Disconnect during playback | Silence output, stop, journal, restore on reconnect |
| Process exits mid-session | Startup recovery runs before other hardware work |
| Global route restore fails | Prominent recovery state, never claim completion |
| Fix worsens result | Stop and offer Original or Last-known-good |
| Fix oscillates | Stop after bounded attempts, offer manual control |

## 18. Testing

### 18.1 Offline tests

- `SimAudioTransport` with deterministic dry and processed fixtures;
- state-machine transition and cancellation tests;
- crash at every transition after snapshot;
- recovery-journal replay and idempotent restore;
- channel-map, dry-loopback, silence, clip, dropout, and latency fixtures;
- repeated-capture stability fixtures;
- adaptive third-pass and unstable-stop fixtures;
- measurement-boundary isolation and stale-claim tests;
- re-amp calibration creation, invalidation, and level-preservation tests;
- route-identity tests that reject plausible audio from the wrong path;
- watchdog, browser-disconnect, ramp, panic-stop, and no-auto-resume tests;
- golden loudness, band, dynamics, stereo, noise, and tail metrics;
- plan revision and stale-confirmation tests;
- shared-channel blast-radius tests;
- fix convergence, worsening, and oscillation tests;
- sensitive-data redaction and opaque-handle tests;
- no-audio-extra installation tests.

Extend `SimFM9` through an injected audio interface. Do not make offline tests
open CoreAudio, ASIO, ALSA, or a real MIDI port.

### 18.2 Measurement corpus

Create versioned, license-safe fixtures at 48 kHz:

- dry DI and known gain changes;
- clean, rhythm, and lead responses;
- clipped, silent, dropout, delayed, and dry-loopback failures;
- known EQ band changes;
- mono, wide, polarity-inverted, and delayed stereo;
- noise and gate envelopes;
- modulation and reverb repeatability cases.

Compare against trusted external meters where applicable. Record tolerances and
the tool/version used to establish them.

### 18.3 Hardware validation, owner only

The owner validates on firmware 11:

1. MIDI and 8x8 audio coexist in the existing ToneCommand process.
2. DI is captured from computer input 5.
3. Re-amp playback on computer output 5 reaches the intended grid input.
4. Processed stereo returns on computer inputs 1/2.
5. Playback level is safe and front-panel monitor behavior is understood.
6. Dry loopback is detected.
7. Global input routing reads, changes, restores, and reads back.
8. Cancel, USB disconnect, browser close, and server restart all recover.
9. Scene changes line up with captured files and effects tails.
10. A known 3 dB output trim produces the expected recorded delta while the USB
    endpoint retains measurable headroom.
11. Re-amp level reproduces the captured DI level closely enough to preserve
    gain, gate, and compression behavior.
12. The server ramps and silences playback when the browser closes, the device
    disconnects, or the player invokes stop.
13. Reconnect does not resume playback or an interrupted transaction.
14. Route-identity controls distinguish correct processed return, dry loopback,
    and a plausible signal arriving on the wrong channel.
15. Isolated-scene and real transition captures produce separate manifests and
    do not share claims.
16. Metric-specific repeatability tolerances are established with event counts,
    95th-percentile spread, and worst-case results.

No simulator result substitutes for these checks.

## 19. Success scorecard

Primary outcome:

> Percentage of player-approved builds whose objective misses are found and
> corrected within two approved passes, without an unintended hardware change.

Guardrails:

- zero observed unapproved persistent writes, with attempted-event count,
  device identity, firmware, and test environment reported;
- zero observed writes outside whitelisted destinations with the same evidence;
- every attempted action has an explicit read-back result;
- every temporary global route has an explicit restore result, with simulated
  and hardware evidence reported separately;
- zero fixes proposed from invalid or unstable captures;
- no `verified` label with zero measurement coverage;
- 95th-percentile and worst-case repeated loudness spread within the validated
  tolerance for supported contexts;
- at least 90 percent of accepted direct loudness fixes reach target within two
  approved passes after calibration, reported with sample size and confidence
  interval;
- zero raw audio, paths, filenames, prompts, or credentials in telemetry;
- track correction rejection, rollback, worsening, instability, and manual
  override rates.

Targets remain hypotheses until hardware baseline data exists.

## 20. Delivery sequence

### Gate 0: feasibility and safety

- Build a standalone, non-writing 48 kHz capture probe.
- Verify device discovery and channel mapping.
- Record processed and DI channels simultaneously.
- Prove dry-loopback detection and safe playback level.
- Decide whether global routing is guided manually or controlled through a
  verified protocol.
- Design and test recovery journaling before temporary routing automation.

### Phase 1: read-only Sound Check

- Optional audio dependency group.
- AudioTransport interface and simulator.
- Personal Calibration Riff.
- Controlled capture twice per scene.
- Validity and repeatability gates.
- Silence, acquisition integrity, USB endpoint headroom, and relative scene
  loudness only.
- No correction yet.

### Phase 2: direct balance correction

- Structured sound policy.
- Coverage-aware result states.
- Per-scene dependency graph.
- Normal Plan revision, server revalidation, digest, Review, Confirm, Send.
- Bounded output-level changes.
- Re-measurement and Original/Last-known-good recovery.

### Phase 3: tonal and stereo evidence

- Calibrated band balance.
- Mid/side, correlation, inter-channel delay, and mono fold-down.
- Dynamics and tail measures.
- Details view and Tone Receipt export.

### Phase 4: directional correction

- One-lever tonal proposals.
- Whole-policy re-evaluation.
- Worsening and oscillation stops.
- Optional bounded sensitivity probes after hardware proof.

### Phase 5: frequency-balance reference comparison

- Golden preset and isolated guitar references first.
- Full-mix broad-estimate behavior.
- Local-only reference handling.

## 21. Definition of done

Sound Check v1 is done when the player can send a preset, press one clear
button, hear the same personal DI pass through every relevant scene, receive a
repeatable scene-balance finding, approve a normal delta plan, and see whether
the correction worked. Temporary routing must restore under success, cancel,
disconnect, and restart.

It is not done if it analyzes different performances as comparable, treats an
empty finding list as a pass, exposes raw DSP as the product, proposes a fix
from unstable audio, mutates a stale browser plan, stores without approval,
claims full tone matching, or requires the owner to trust a simulator for USB
audio behavior.

## 22. Source-of-truth references

- [FM9 owner's manual](https://www.fractalaudio.com/downloads/manuals/FM9/FM9-Owners-Manual.pdf)
- [FM9 downloads and current firmware](https://www.fractalaudio.com/fm9-downloads/)
- [python-sounddevice documentation](https://python-sounddevice.readthedocs.io/)
- [PySoundFile documentation](https://python-soundfile.readthedocs.io/)
- [SciPy signal processing](https://docs.scipy.org/doc/scipy/reference/signal.html)
- [pyloudnorm](https://github.com/csteinmetz1/pyloudnorm)

Recheck device routing and library behavior at implementation time. The FM9
manual and firmware are versioned dependencies.
