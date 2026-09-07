# ToneCommand Next-Level Product Experience

Status: product and interaction specification only, no implementation authorized  
Updated: 2026-09-07  
Detailed IR specification: `../../ir-command/docs/PRODUCT-DESIGN-V2.md`  
Detailed Sound Check specification: `SOUND-CHECK-DESIGN.md`  
Desktop visual specification: `UI-REDESIGN-SPEC.md`

## 1. Executive decision

ToneCommand is not an editor, search engine, or automated mastering tool. It is
a trusted command system for a guitarist's sound.

The complete product promise is:

> Tell ToneCommand what you want. Hear the smallest set of meaningful choices.
> Approve one precise plan. Let it command the FM9 safely. Hear and see proof
> that the result moved in the intended direction.

The product loop is:

`ASK -> UNDERSTAND -> HEAR -> CHOOSE -> REVIEW -> CONFIRM -> SEND -> PROVE -> REMEMBER`

The permanent workflow remains:

`REQUEST -> PLAN -> REVIEW -> CONFIRM -> SEND`

Listening, measurement, learning, and proof strengthen those five stages. They
do not become more modes, tabs, or setup chores.

The opponent is not a competing preset editor. The opponent is uncertainty:

- Which of thousands of owned sounds is worth hearing?
- What will this change affect?
- Did the intended values reach the correct hardware location?
- Did the audible result improve?
- Can the player get back to the last trusted version?
- Will the rig still behave correctly at rehearsal, after a firmware update,
  and across a complete set?

ToneCommand wins when every one of those questions has a calm, immediate,
evidence-backed answer.

## 2. The product moat

The moat is a private, compounding decision loop rather than a larger content
catalog or more AI-generated parameters.

```text
Player intent
     |
     v
Compatible possibilities -> controlled listening -> explicit choice
     ^                                                 |
     |                                                 v
Current rig context <- personal tone memory <- verified outcome
```

Each accepted choice improves future recommendations for that player's guitar,
pickup, tuning, role, and rig. Each Send creates evidence. Each Sound Check
creates a repeatable baseline. Each receipt makes the system safer to trust.

This creates four durable advantages:

1. **Owned-library intelligence.** ToneCommand makes sounds the player already
   owns usable again.
2. **Contextual taste memory.** It learns from explicit listening decisions,
   not generic genre stereotypes.
3. **Hardware-grounded proof.** It distinguishes a plausible plan from a result
   read back and measured on the actual unit.
4. **Continuity over time.** It can detect drift across scenes, presets,
   setlists, guitars, and firmware versions.

No cloud account is required for the moat. The player's audio, choices,
fingerprints, and history remain local by default.

### 2.1 One product, clear feature language

The player uses one product: **ToneCommand**. IRCommand remains an internal
engine or developer-facing service name.

Player-facing capability names are:

- **Cabinet Intelligence:** finds, compares, and prepares compatible owned
  cabinet sounds;
- **Sound Check:** measures a named result at a named boundary;
- **Tone Memory:** remembers explicit contextual choices;
- **Tone Receipt:** explains and exports a trusted Tone Version;
- **Rig Confidence:** checks continuity across scenes, presets, setlists, and
  time.

Safety, recovery, attribution, and read-back are product foundations. They are
never presented as premium add-ons.

## 3. The seven product primitives

Every feature must strengthen at least one of these primitives. Features that
do not are distractions.

| Primitive | What it contains | Player value |
|---|---|---|
| Tone Goal | Requested result, context, priorities, and preserved qualities | The system understands the job, not just keywords |
| Rig State | Device identity, firmware, preset state, scenes, signal graph, guitar profile | Recommendations fit the real setup |
| Listening Set | Current plus one to three controlled, meaningfully different candidates | Decisions happen by ear without option overload |
| Plan Revision | Immutable server-validated actions and complete blast radius | Review and Send always refer to the same thing |
| Proof | Read-back, controlled comparison, coverage, uncertainty, and restore result | The system earns trust instead of asking for it |
| Tone Memory | Explicit choices and verified outcomes, conditioned on context | The product becomes personally better over time |
| Tone Version | The canonical lineage node joining all of the above | Any trusted result can be understood, compared, or restored |

The Tone Receipt is the human-readable and exportable view of a Tone Version.

### 3.1 Tone Version

Every request creates or branches a Tone Version. A Tone Version contains:

- the original request and structured Tone Goal;
- guitar, pickup, tuning, role, monitoring context, and player-named anchor;
- exact device, firmware, preset, scene, graph, and relevant global state;
- source assets, licenses, attribution, and transform lineage;
- alternatives auditioned and the player's explicit decisions;
- immutable Plan Revision and recovery snapshot;
- parameter read-back evidence;
- Sound Check evidence and its exact measurement boundary;
- player verdict: chosen, kept, rejected, restored, or worked in a named field
  context;
- parent, child, Original, Previous, Current, and Last-known-good relationships;
- invalidation reasons when firmware, assets, state, or context changes.

Search, audition, Send, Sound Check, recovery, receipts, and sharing all operate
on this object. They must not become disconnected feature databases.

## 4. Signature experience one: the Tone Goal

### 4.1 A musical contract, not a prompt transcript

Every request becomes a compact Tone Goal with seven fields:

- **Make:** what should become more true;
- **Keep:** what must not be lost;
- **Avoid:** what must not be introduced;
- **Listen for:** subjective qualities only the player can decide;
- **Verify:** measurable acceptance criteria;
- **Context:** guitar, pickup, tuning, role, scene, and reference when known;
- **Unknown:** relevant facts ToneCommand refuses to invent.

Example:

```text
MAKE
Tighter Drop C rhythm with a smoother top

KEEP
The low-mid weight and pick attack you already have

AVOID
More gain, more 57 bite, or a level change

LISTEN FOR
Whether the result still feels immediate
```

Context appears on one quiet line:

```text
7-string | Drop C | Bridge pickup | Rhythm
```

ToneCommand infers only what is supported. An inference appears as a removable
chip, never as a hidden fact. It asks a question only when two materially
different safe plans remain and the answer cannot be learned by audition.

### 4.2 Lock What You Love

The player can say `keep the body`, `do not touch the delay`, or `leave every
other scene alone`. ToneCommand turns these into scoped constraints.

There are three kinds of lock:

1. **Exact lock:** a parameter, block, scene, or destination cannot change.
2. **Structural lock:** topology, channel assignment, controller, or routing
   cannot change.
3. **Outcome guard:** a measurable property may not worsen beyond repeatability
   tolerance.

Subjective language such as `keep the feel` is preserved as an intent reminder
and audition requirement. It is never silently converted into a fake numeric
guarantee.

### 4.3 Acceptance criteria

When the player states a measurable target, it becomes part of the Tone Goal:

- `lead about 2 dB above rhythm`;
- `no louder than the current scene`;
- `keep mono compatibility`;
- `keep the FM9 USB output below my saved headroom limit`.

ToneCommand may suggest a target from the player's saved rulebook, but the UI
labels it as a suggestion. Style conventions never become hidden hard rules.

## 5. Signature experience two: the Listening Loop

### 5.1 The shortest path from words to ears

Search results are not the product. The first comparison is Current versus the
strongest supported recommendation. Alternatives appear only when they improve
the decision.

Candidate roles are:

- **Best fit:** closest supported match to the complete Tone Goal;
- **Refinement:** preserves the current character while changing the requested
  quality;
- **Different direction:** a credible contrast that helps the ear decide.

The player can ignore names and choose by sound. Candidate identity remains
available but secondary. There may be one, two, or three candidates. Filling
three slots is never a goal.

```text
HEAR THE DIFFERENCE

    CURRENT             A                 B                 C
                      BEST FIT         REFINEMENT      DIFFERENT DIRECTION

        [                 continuous phrase loop                 ]

  [CURRENT] [A] [B] [C]       MATCHED LEVEL ON       [BLIND]

  A keeps the weight and removes the most upper-mid bite.
              [CHOOSE A]                  [KEEP CURRENT]
```

### 5.2 Audition integrity

Every comparison must use:

- Current as a permanent one-key baseline;
- the exact same DI performance and active region;
- identical amp, input, scene, and non-cab state;
- onset-aligned candidates;
- phrase-boundary switching without a timing jump;
- loudness-matched listening by default;
- raw-level listening as an explicit alternate view;
- captured source and renderer hashes in evidence.

If those facts are not true, the UI calls it a preview, not a comparison.

### 5.3 Preview fidelity

Every audible candidate carries one internal fidelity grade:

| Grade | Meaning | Player copy |
|---|---|---|
| `target_in_chain` | Exact FM9 amp path and target-rendered cab asset | Heard in your rig |
| `captured_pre_cab` | Exact current pre-cab amp output convolved locally | Heard from your amp path |
| `representative_amp` | Fixed licensed pre-cab source | Representative preview |
| `metadata_only` | No trustworthy audio render | Not auditioned |

A dry DI convolved directly with a cabinet IR is not a valid cabinet audition
because it omits the nonlinear amp stage. Source-WAV preview and the eventual
FM9 rendering must not be presented as equivalent until hardware comparison
supports that claim.

### 5.4 Use the right phrase

A Guitar Card divides the player's Calibration Riff into named moments:

- `CHUG`: palm-muted transient rhythm;
- `RING`: sustained chord and decay;
- `LEAD`: upper-register single notes;
- `CLEAN`: dynamic low-to-high playing;
- `REST`: hands-off analog noise.

ToneCommand picks the phrase that best exposes the requested difference.
`Tighter` starts with CHUG. `Less bite` uses RING and LEAD. `Gate` uses REST
plus the first note onset. The active phrase is visible and changeable.

### 5.5 Ear-first controls

The listening surface supports mouse, keyboard, MIDI footswitch, and accessible
list navigation. It never requires watching the screen during a decision.

Recommended controls:

- `1`, `2`, `3`, and `4` select Current and candidates;
- space starts and stops the loop;
- left and right arrows change the active phrase;
- Escape immediately stops audio;
- blind mode reveals identity only after a choice is recorded;
- a connected footswitch may cycle, choose, reject, and replay;
- undo restores the prior listening choice without changing hardware.

Keyboard bindings are remappable and never intercept text-entry fields.

### 5.6 The Tone Compass

When the player asks for another direction, the product offers a relative
neighborhood rather than a wall of search results.

```text
                         SMOOTHER TOP
                              C
                              |
                 MORE BODY -- A -- TIGHTER LOW END
                              |
                              B
                         MORE OPEN
```

The directions come from the current Tone Goal and supported evidence. They are
not universal acoustic axes. Each direction opens another small Listening Set
while preserving locked qualities.

The Tone Compass must also have a list representation for keyboard and screen
reader use. Color and geometry never carry meaning alone.

### 5.7 Say the delta

After any audition, the player can continue naturally:

- `A, but halfway toward B`;
- `keep A's body and lose a little more bite`;
- `none of these, stay closer to what I have`;
- `that is right for rhythm, now make the lead related but wider`.

The next set derives from the prior decision and its locks. The product does
not discard context and rerun a generic search.

## 6. Signature experience three: Personal Tone Memory

### 6.1 Learn choices, not assumptions

Tone Memory learns only from explicit evidence:

- A beat B in a labeled comparison;
- B beat C in a blind comparison;
- the player kept or restored a verified result;
- the player explicitly marked a quality to preserve or avoid;
- the player named a sound as a Trusted Anchor;
- the player optionally said it worked at rehearsal or in another named
  context.

Previewing, scrolling past, hovering, or failing to click is not negative
feedback. A measurement improvement does not become Last-known-good until the
player keeps it.

### 6.2 Context is part of preference

There is no single global `Moncy likes dark tones` score. A choice is conditioned
on:

- guitar and pickup;
- tuning;
- musical role;
- amp family and gain range;
- current cabinet or capture;
- monitoring context;
- labeled versus blind audition;
- matched versus raw level;
- request and preserved qualities.

The same player can prefer a bright 57 blend for a dense rhythm and a darker
ribbon for an exposed lead without the model treating that as contradiction.

### 6.3 Trusted Anchors

The player may name a result:

- `My Drop C rhythm`;
- `Recording clean`;
- `Live lead reference`;
- `Before firmware 12`.

A Trusted Anchor is a Tone Version, not just a preset file. Future requests can
say `give this clean the same width as Recording clean` or `do not move farther
from My Drop C rhythm`.

### 6.4 Memory controls

The player can inspect, correct, export, pause, reset, or delete Tone Memory.
The visible explanation stays human:

> For Drop C rhythm on this guitar, you have usually chosen less 57 and more
> ribbon than the closest catalog match.

After enough consistent choices, the system asks before adopting a learned
pattern. Early sessions deliberately retain exploration so a few choices do
not create a filter bubble.

### 6.5 Personal Tone Language

Tone Memory also learns how this player uses ambiguous words such as `nasty`,
`chewy`, `papery`, `finished`, or `three-dimensional`. It does not define those
words from a generic dictionary. It observes repeated, context-matched choices
and asks before saving an interpretation:

```text
In Drop C rhythm comparisons, "nasty" has usually meant the 57-forward
upper-mid character. Use that meaning in future rhythm requests?

[YES]   [NOT YET]
```

The interpretation remains scoped to the relevant context and retains the
examples that support it. The player can correct or delete it. An occasional
Different direction candidate may test an uncertain preference boundary, but
never at the expense of the strongest supported option.

## 7. Signature experience four: Prove It

### 7.1 One proof card

After Send, the first result is not a log. It is one answer:

```text
SENT AND VERIFIED

Your tighter rhythm is active on the FM9.
18 approved changes read back correctly. No other scene changed.

                  [PLAY IT]       [CHECK THE SOUND]
```

When measurable promises exist, Confirm may offer `SEND AND CHECK` as the
recommended primary action and `SEND ONLY` as the secondary action. One consent
covers that exact bounded send and measurement transaction. It does not grant
ongoing authority.

After Sound Check:

```text
CLOSER TO TARGET

Upper bite moved 1.9 dB closer to your trusted rhythm.
Level stayed within 0.2 LU. Pick attack remained inside your guard.

            [HEAR BEFORE / AFTER]       [KEEP THIS VERSION]
```

The card distinguishes:

- **Sent:** commands were transmitted;
- **Read back:** the FM9 reported the intended state;
- **Sound checked:** controlled output was captured at a named boundary;
- **Closer to target:** the stated measurable criterion moved correctly;
- **Your pick:** the player preferred it;
- **Kept:** the player explicitly retained the version;
- **Field noted:** the player reported an outcome in a named context.

These words are never interchangeable. `Better` belongs to the player.

### 7.2 Before and after truth

Before and After uses the same DI, aligned regions, equal monitoring path, and
optional matched loudness. The first comparison is blind when practical. Raw
level and exact metrics remain available after the listening decision.

The system shows predicted versus observed effect:

```text
EXPECTED                         OBSERVED
Less upper bite                  1.9 dB less from 6 to 10 kHz
No scene-level change            +0.2 LU, inside repeatability
Rhythm scenes only               Scenes 1 and 3 changed, as reviewed
```

It then asks for the human verdict:

```text
The result reached the requested balance. How does it feel?

[BETTER]   [DIFFERENT, NOT BETTER]   [PREFER ORIGINAL]
```

If a change did not help, the product says so plainly and offers Original or
Last-known-good. It never reframes failure as success.

### 7.3 Evidence depths

Every result has exactly three depths:

1. **Glance:** one outcome, one primary action, one safety fact;
2. **Inspect:** affected scenes, before and after, confidence, remaining
   unknowns;
3. **Forensic:** hashes, manifests, policy version, measurements, device reads,
   provenance, and diagnostic log.

Machinery never leaks upward merely because it exists.

### 7.4 Tone Timeline

Every session has a simple branchable history:

```text
ORIGINAL -> CAB B -> LEVEL FIX -> YOUR PICK
```

Any checkpoint can be heard again. Restoring one creates a normal reviewed and
confirmed plan. It never causes a blind write. A branch preserves later work
instead of overwriting history.

## 8. Signature experience five: Rig Confidence

Sound Check should grow from checking one preset to protecting a professional
rig across time. These capabilities remain read-only until the player approves
a normal correction plan.

### 8.1 Setlist Assurance

The player says:

> Check tomorrow's set and tell me what could surprise me.

ToneCommand replays the appropriate personal DI through the selected presets
and scenes, then reports only actionable outliers:

- unexpected level jumps between adjacent songs;
- a clean that disappears relative to the set baseline;
- a lead that exceeds the player's saved maximum lift;
- unexpected silence, low USB endpoint headroom, missing stereo side, or severe
  mono cancellation;
- a preset whose state no longer matches its last Trusted Anchor;
- scenes or transitions that could not be checked.

Level comparisons span only Tone Versions with the same valid Guitar Card and
re-amp calibration. Different guitars or pickups use separate baselines unless
the player has created an explicit cross-Guitar Card level calibration. An
uncalibrated change of guitar produces `not comparable`, never a fabricated
set-wide loudness rank.

The overview is a setlist timeline with no more than one primary concern per
song. Corrections are separate normal plans. `Check the set` never means `edit
the set`.

### 8.2 Transition Check

Static scenes can measure correctly while the live change between them fails.
Transition Check captures named performance moves such as:

`Rhythm scene 1 -> Lead scene 4 -> Rhythm scene 1`

It can evaluate, after hardware calibration:

- switching gap or unexpected transient;
- delay and reverb spillover behavior;
- tempo-synchronized repeat continuity;
- abrupt stereo or level collapse;
- modifier and expression position dependency;
- whether the return transition restores the expected sound.

The MIDI event and audio capture share a clock so the result can be tied to the
actual transition. Isolated-scene and transition measurement are separate
protocols. Until measured tolerances exist, timing is descriptive and never
labeled pass or fail.

### 8.3 Firmware Drift Guard

Before an FM9 firmware update, ToneCommand offers to preserve a read-only
baseline for Trusted Anchors. After the update, the same DI and measurement
manifest are replayed.

The result distinguishes:

- preset data changed;
- parameter interpretation changed;
- measured output changed while stored state appears the same;
- measurement conditions changed, making comparison invalid;
- no meaningful change above repeatability tolerance.

Drift Guard says `changed since the prior capture`. It does not blame firmware
unless firmware is the only observed variable. It never promises bit-identical
sound and never rolls firmware back.

### 8.4 Rig Readiness

Before rehearsal or a show, one read-only check can verify:

- expected device and firmware;
- selected setlist presets are present;
- required user cabs are present and identifiable;
- no incomplete recovery transaction exists;
- current preset and scene states are known;
- latest Setlist Assurance results and unresolved concerns;
- an exportable recovery bundle is available.

The outcome is player language without a universal readiness claim:

> 12 songs match their checked versions. One transition remains unchecked.

Rig Readiness never stores, changes routing, or launches audio unless the
player separately approves the named check.

### 8.5 Stage Lock

Stage Lock is a deliberate read-only performance state. It prevents Send and
setup changes, shows the active preset and the 4 by 2 Scene Deck with full scene
names, and keeps an emergency audio stop available. Exiting requires an
explicit desktop action, not a footswitch that could be hit accidentally.
Stage Lock never blocks a required recovery restore or emergency audio stop.

### 8.6 Rehearsal markers

During live observation, the player can mark `harsh here`, `lead disappeared`,
or `keep this` by footswitch or keyboard. ToneCommand links the marker to local
audio time, active preset, scene, guitar card, and controller state. Later the
player can say `fix the harsh part I marked` without recalling technical facts.

A marker is evidence of a moment, not permission for an automatic correction.

## 9. Signature experience six: Context Lens

A tone that is impressive alone can fail in the arrangement. Context Lens lets
the player audition against local, player-supplied musical context.

Supported views:

- **Solo:** the controlled guitar result;
- **In the mix:** the same result against a local backing loop or stem;
- **Mono:** fold-down compatibility;
- **Quiet:** level-compensated low-monitoring preview;
- **Raw:** no audition loudness compensation.

The product never claims that a local backing loop represents the venue, PA,
room, mastering chain, or audience position. It simply provides a consistent
decision context.

References remain local by default. Copyrighted audio is never uploaded or
shared without a separate explicit action.

## 10. Advanced exploration: find the sweet spot

This is a later capability, gated behind the trustworthy catalog and audition
system.

When the player says `halfway between A and B`, IRCommand may create a temporary
phase-aware blend only when:

- both inputs are compatible cabinet IRs;
- their onset, polarity, and phase relationship can be aligned safely;
- the combined headroom is controlled;
- both licenses permit the local derivative;
- complete parent provenance is retained;
- the original assets remain immutable.

The player auditions a small continuum and chooses by ear. The selected blend
becomes an immutable derived asset with both parents in its Tone Receipt.

Where the verified target can run multiple cabinet sources natively, prefer a
Cabinet Recipe over baking a new file. The recipe names each source plus gain,
pan, polarity, delay, alignment, target block, and channel. It reports phase and
comb-filter risk, uses only controls present in the device capability profile,
and is auditioned through the actual recipe. One immutable recipe identity and
receipt bind the complete result.

If alignment is unreliable or the licenses conflict, `halfway` means retrieve
a third existing candidate between their audible traits. It never means make an
untraceable file blend.

## 11. Unified interaction architecture

### 11.1 One front door

There is one request field. The player never selects build, modify, source,
empty-slot, IR search, measurement, setlist, or recovery modes.

Examples:

- `Build me a tight Periphery-inspired Drop C rhythm.`
- `Keep the body, but the 57 is getting nasty.`
- `Use this link and load the three FM9 presets.`
- `Make scene 4 about 2 dB above scene 1.`
- `Check the whole set for level surprises.`
- `Did firmware 12 change my trusted cleans?`

The interface routes internally and voices its understanding in the Plan.

### 11.2 The five permanent stages

| Stage | One player question | Primary surface | What stays hidden |
|---|---|---|---|
| Request | What do I want? | Natural-language composer with current target context | Modes, endpoints, planner selection |
| Plan | What will ToneCommand do? | Goal, proposed musical result, decisions needing ears | Raw action list and protocol |
| Review | What changes and what could it affect? | Before/after values, dependencies, locks, evidence | Unchanged parameters and routine checks |
| Confirm | Am I authorizing this exact result and destination? | Immutable plan summary, destination, recovery fact | Repeated rationale and diagnostics |
| Send | Did it happen? | Progress, read-back, proof, next musical action | Message traffic and retry mechanics |

Sound Check, audition, and recovery appear as contextual actions inside those
stages. They never expand the permanent navigation.

### 11.3 Ear-first Review

Review has three layers in this order:

1. musical outcome and Tone Goal;
2. Current versus Proposed audible comparison;
3. exact changes, affected scope, and evidence.

The first view names both change and protection:

```text
WHAT WILL CHANGE
Cabinet becomes tighter and less 57-forward
Lead rises slightly above Rhythm

WHAT STAYS PROTECTED
Amp choice, gain structure, and delay character
Scenes 1, 3, 4, 5, 6, 7, and 8
```

The Scene Deck is a 4 by 2 grid. Every tile has a two-line full scene name,
role, change count, and status. Scene names never clip and hover is never
required. Editing a value creates a new server-validated revision, refreshes
the audible proposal, and disarms Confirm until validation completes.

### 11.4 Confirm as one command sentence

```text
Send this cabinet and 6 adjustments to
FM9 | Preset 133 | Modern Drop C

Protected: one preset, one cab slot
Restore point ready

                         [SEND TO FM9]
```

Destination, persistence, blast radius, and recovery readiness are never
hidden. The only secondary action is `Back to Review`.

### 11.5 Send as physical proof

The motion sequence follows real state:

```text
Protecting current sound
Sending the approved changes
Checking the FM9
VERIFIED ON FM9
```

A restrained signal pulse may travel from the plan to a dimensional FM9 tile.
Verification appears only after read-back. The emotional payoff is precision,
not confetti.

### 11.6 Decision density

At any moment the main surface shows:

- one outcome statement;
- no more than three new choices plus Current;
- one primary action;
- one reversible secondary action;
- one path to evidence.

If more information is required, group it behind `See impact`, `Why this`, or
`Technical record`. Do not solve density by shrinking type, reducing hit areas,
or filling every empty space.

### 11.7 Visual behavior

The interface should feel like precision hardware under human command:

- large 64 to 72 pixel machined hexagonal stage indicators represent the five
  command stages;
- an active stage appears energized from within, not filled with a flat color;
- beveled dimensional icons are reserved for primary physical concepts such as
  guitar input, plan, shielded review, authorization, FM9 send, listening, and
  verified return;
- every icon shares one camera angle, light source, material palette, edge
  bevel, and silhouette weight;
- raised surfaces mean actionable, inset surfaces mean evidence, illuminated
  edges mean active hardware state, and engraved checks mean verified;
- cards use broad dark surfaces, strong depth separation, and generous spacing;
- orange indicates commanded energy, cyan indicates verified return, green is
  reserved for a completed safety fact, amber means attention, and red means a
  blocked action;
- animation communicates state transfer and verification, never decoration;
- reduced-motion mode replaces travel and glow with immediate state changes.

No technical state is conveyed by color, icon, glow, or animation alone.

## 12. Command state and proof model

Every meaningful interaction belongs to one append-only Tone Session:

```text
ToneSession
  ToneVersions[]
    ToneGoal
    ContextSnapshot
    ListeningSets[]
    ExplicitChoices[]
    PlanRevisions[]
    Confirmation
    HardwareTransaction
    SoundChecks[]
    ToneReceipt
    MemoryEvents[]
```

A revised goal or editable value creates a new revision. It never mutates the
evidence for a prior decision.

### 12.1 Required identity bindings

A confirmed action binds:

- device identity and firmware;
- target preset and semantic state digest;
- plan id, revision, and action digest;
- affected blocks, channels, scenes, slots, and globals;
- recovery snapshot identity;
- Tone Goal and preserved locks;
- chosen asset and provenance when applicable;
- measurement source and target when applicable.

Any relevant change disarms Confirm. The player sees `The FM9 changed, so I
refreshed the plan` rather than a digest mismatch.

### 12.2 Proof vocabulary

These status words have exact meanings:

| Word | Required evidence |
|---|---|
| Ready | Preconditions known and validation passed, nothing sent |
| Confirmed | Player authorized one immutable revision |
| Sent | Commands completed without transport failure |
| Verified | Intended device state read back and matched |
| Sound checked | Valid controlled capture produced repeatable metrics at a named boundary |
| Closer to target | Named measurable criterion moved favorably without breaking guards |
| Your pick | Player selected the result in an audition |
| Kept | Player explicitly retained the version |
| Field noted | Player reported the result in a named real-world context |
| Restored | Prior state was reapplied and read back |

Every badge states its scope. A version Sound checked with one Guitar Card is
not globally verified. Relevant firmware, asset, routing, or state changes mark
only the affected proof as stale.

`Safe`, `perfect`, `sounds right`, and `gig-ready` are not machine conclusions.

## 13. Recovery as an experience

Recovery should feel like returning a physical control surface to a known
position, not troubleshooting software.

Normal recovery card:

```text
FM9 RESTORED
The temporary sound check ended. Your original routing and scene are back.
```

Interrupted recovery card:

```text
FINISHING THE RETURN
ToneCommand found an interrupted sound check. Keep the FM9 connected while it
returns the temporary settings. No new changes can be sent yet.
```

Unknown recovery state:

```text
CHECK THE FM9
ToneCommand could not prove that one temporary setting returned. Sending is
paused. Your recovery record is ready.
```

The technical record may identify the exact setting. The primary surface must
not show a raw exception or protocol message. Browsing, planning, and local
audition remain usable while hardware actions are paused.

## 14. Experience rules for intelligence

### 14.1 The system may decide internally when

- the choice is reversible and does not touch hardware;
- compatibility or safety has one correct answer;
- a retry is bounded and cannot duplicate a persistent action;
- a default has been explicitly saved by the player;
- the result can be validated before it affects a recommendation.

### 14.2 The system must involve the player when

- two audible directions are both defensible;
- a subjective quality is the deciding fact;
- a new or broader hardware destination would be affected;
- an external download, authentication, upload, or license decision begins;
- a persistent write is about to occur;
- a correction trades one preserved quality against another;
- evidence is too weak to make a safe recommendation.

### 14.3 The system must stop when

- device identity or relevant state changed;
- the recovery snapshot is incomplete;
- audio validity or repeatability failed;
- a correction worsened the target or introduced a hard concern;
- rights or asset compatibility are uncertain;
- the requested outcome cannot be measured or safely inferred;
- the player cancels.

## 15. Accessibility requirements

- Every status uses text, icon, and color.
- Complete operation is possible by keyboard, with shortcuts disabled during
  text entry.
- Audition switching and emergency stop can use a footswitch.
- Interactive targets are at least 44 by 44 pixels and have visible focus.
- Scene names wrap to two lines and never depend on hover.
- Screen-reader labels describe candidate, selection, compatibility, proof,
  and hardware destination.
- Live meters do not flood screen-reader announcements.
- Reduced-motion mode removes signal travel and depth animation without hiding
  state.
- High-contrast mode preserves the retro-metal identity.
- Audio never starts at an uncapped level. Monitoring caps are saved per
  device.
- Countdowns are visual and optionally audible.
- Drag and drop is never the only way to add a library or reference.

## 16. Rights-respecting ecosystem

These are later extensions. They must never require uploading a player's local
library, paths, hashes, audio, prompts, or preference history.

### 16.1 Signed creator manifests

Creators may publish signed manifests containing public asset identifiers,
hashes, cabinet and capture metadata, compatible formats, license, attribution,
and pack relationships. IRCommand can enrich an owned file locally without
revealing that the player owns it.

### 16.2 Portable Tone Recipes

A recipe contains intent, Tone Goal, device requirements, parameter graph or
validated deltas, public asset references, measurement method, scoped result,
attribution, and unknowns. It never includes a protected IR or model binary.

The recipient resolves assets through files they own or an authenticated
provider. When an asset is unavailable, ToneCommand explains what is missing
and can find a compatible owned substitute.

### 16.3 Capability evidence

Signed, versioned capability profiles may accept narrowly scoped, maintainer-
reviewed hardware results such as supported actions, read-back behavior,
routing behavior, restoration tests, and firmware exceptions. No personal tone
data is needed.

## 17. Anti-features

The following would make the product look advanced while weakening it:

- a dashboard full of FFTs, LUFS meters, model confidence, and catalog counts;
- a universal tone score;
- a button labeled `optimize everything`;
- autonomous multi-pass hardware correction;
- infinite AI-generated candidate lists;
- treating a genre label as the player's taste;
- uploading the player's library or DI to create the appearance of cloud
  intelligence;
- silently normalizing every preview;
- claiming a full mastered song can be tone-matched exactly;
- calling parameter read-back audible verification;
- calling an unchecked rig gig-ready;
- encouraging more changes after the Tone Goal is already satisfied;
- a separate player-facing IRCommand application;
- social feeds, likes, rankings, or marketplaces before the private loop works.

Restraint is part of the premium experience.

## 18. Feature dependency and delivery order

The implementation sequence follows trust, not spectacle.

### Gate 0: prove device and rights seams

- hardware-prove every temporary and persistent FM9 path on firmware 11;
- prove exact audio routing, safe levels, restore, and interruption recovery;
- resolve the supported WAV-to-FM9 handoff;
- resolve TONE3000 product tier, OAuth, search, attribution, and storage terms;
- keep undocumented target formats out of committed scope.

### Phase 1: earn one excellent listening decision

- trustworthy local catalog and conservative classification;
- Tone Goal with Keep, Avoid, Listen for, Verify, and Unknown;
- Current plus an adaptive one-to-three candidate Listening Set;
- real fixed-source, onset-aligned, matched and raw audition;
- explicit choice, Tone Version, and Tone Receipt.

Exit condition: a player can find and choose a buried owned IR faster and more
confidently than browsing folders. A warm first audition target is under five
seconds.

### Phase 2: prove one requested outcome

- immutable Plan Revision across Review, Confirm, and Send;
- read-only Sound Check;
- capture validity, coverage, and adaptive repeatability;
- Before and After listening;
- direct level correction through the normal approval flow.

Exit condition: the product can prove one measurable request moved closer to
target without claiming subjective judgment.

### Phase 3: become personally better

- contextual Tone Memory;
- Trusted Anchors;
- Tone Compass;
- delta language such as `A, but smoother`;
- prediction versus observation calibration.

Exit condition: repeat players prefer the personalized shortlist over an
unpersonalized baseline in blind evaluation.

### Phase 4: protect the professional rig

- Setlist Assurance;
- Transition Check;
- Firmware Drift Guard;
- Rig Readiness, Stage Lock, and recovery bundle;
- rehearsal markers and Context Lens.

Exit condition: a player finds a real set-level surprise before rehearsal and
can reproduce the evidence.

### Phase 5: advanced exploration

- phase-aware cabinet sweet spots;
- hardware-calibrated sensitivity maps;
- additional capability-proven devices;
- signed creator manifests, portable recipes, and capability evidence.

Exit condition: each advanced feature improves blind listening decisions, not
merely engagement or catalog activity.

## 19. Evaluation plan

### 19.1 Five-second comprehension

Show a fresh player each stage for five seconds, then ask:

- what did you ask for?
- what will change?
- what will stay untouched?
- what choice is required now?
- has anything reached the FM9 yet?

At least 90 percent should answer all five correctly before visual polish is
considered complete.

### 19.2 Listening quality

Measure:

- time from request to first meaningful audition;
- time from request to confident choice;
- recommendation chosen versus Current retained;
- blind preference against current manual browsing;
- percentage of sets where every candidate is meaningfully distinct;
- personalized versus unpersonalized blind win rate;
- choices reversed in-session and within seven days;
- player-rated decision confidence;
- percentage completed without mouse or trackpad.

A confident `Keep current` and `No preference` are successful outcomes.

### 19.3 Trust quality

Measure:

- correct understanding of Sent, Verified, Sound checked, and Kept;
- stale-plan and stale-proof detection;
- unexpected blast-radius reports;
- restore and rollback success with event counts and hardware coverage;
- false-safe compatibility rate with confidence intervals;
- invalid measurement rejection rate;
- percentage of receipts that can reproduce the reported evidence.

Safety evidence reports event counts, device and firmware coverage, and
confidence bounds. Rounded percentages must not imply more evidence than the
corpus supports.

### 19.4 Professional value

Measure:

- level and transition surprises caught before rehearsal;
- Trusted Anchors rechecked after firmware changes;
- time to certify a set compared with manual checking;
- versions kept after a later rehearsal note;
- correction acceptance, regret, and rollback rates;
- percentage of sessions resolved using already-owned assets;
- number of unresolved unknowns surfaced before a show.

Success is not clicks, prompts, or minutes spent. It is faster confident
decisions, fewer surprises, fewer unnecessary changes, and complete recovery.

## 20. Definition of unbeatable

The design reaches its north star when a professional player can say:

> Keep what I like about this rhythm, remove the harshness, make the lead sit
> two dB above it, and check tomorrow's set.

ToneCommand must then:

1. preserve the existing musical and hardware context;
2. retrieve or propose only eligible choices;
3. let the player decide audible ambiguity by ear;
4. show one immutable, complete blast radius;
5. send only the confirmed revision through existing protections;
6. read back every affected state;
7. replay the same personal performance for controlled evidence;
8. verify only the outcomes it can genuinely measure;
9. stop and restore if evidence or safety fails;
10. remember the explicit choice locally for the next relevant request;
11. provide a receipt that another person can audit;
12. identify any remaining set-level or firmware-drift uncertainty.

It is not unbeatable because it claims to have better ears than the player. It
is unbeatable when the player keeps creative authority while the machine makes
search, repetition, comparison, bookkeeping, safety, and proof disappear.
