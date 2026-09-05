# FM9 tone-building rules

The rulebook the planner reads and operates by on every build, and that any
agent working on ToneCommand follows. If a build breaks one of these rules, the
build is wrong, not the rule. Many rules came from real failures (a blind Marco
Sfogli build compared to the pro preset, 2026-09-04, and builds after it); the
dated lines are here because the tool got it wrong once.

How to read this file:
- Part A (rules 1-7) are the UNIVERSAL guardrails. They apply to every build,
  every role. They keep a build from being broken.
- Part B (rules 8-11) are the ROLE PLAYBOOKS: clean, rhythm, lead, and the
  effects that serve each. A clean is not a quiet rhythm; a lead is not a loud
  rhythm. Each role has its own targets. Build each scene to its role's
  playbook, never one setting sprayed across all three.
- Part C (rules 12-14) are the CEILING-RAISERS and the pre-ship check: width,
  depth, realism, and the test that keeps a build from shipping bland.

The bar: a build that passes Part A is not broken. A build that also follows the
right role playbook (Part B) and passes the self-check (rule 14) is one a player
can gig as-is, with minimal tweaking. Ship that kind.

================================================================================
PART A - UNIVERSAL GUARDRAILS (every build, every role)
================================================================================

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
- One amp block has only 4 channels, and a block's params live on the channel,
  shared by every scene using it. So a build can hold at most 4 distinct amp
  voices across its scenes. When a request asks for more scenes than that, put
  the COMPATIBLE roles on a shared channel (clean and funk on one, blues and
  crunch on another, rock and metal on another, lead and its variant on the
  last) and differentiate those scenes with effects and bypass, not with amp
  EQ they cannot independently change. Say in the summary which roles share a
  channel and why. Never silently give two scenes the same voice with no
  difference.

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
  FAR more than looks right on paper. Near 0 is NOT enough: a clean that shipped
  at DISTORT_LEVEL 0 was "much too quiet" on hardware and only sat right at +15
  to +18 (2026-09-05, an 80s tribute audited scene by scene with the owner).
  Do not cut the level of an already-weak scene.
- CLEAN-VS-DISTORTED LEVEL SPREAD IS LARGE. A distorted amp makes far more raw
  output than a clean one at the SAME LEVEL, so to sit at equal PERCEIVED
  loudness the clean amp's DISTORT_LEVEL runs about +15 to +18 while the
  distorted rhythm/lead amps run about -10 to -12: roughly a 25-30 dB spread in
  the LEVEL param that lands them even by ear (2026-09-05, verified scene by
  scene). Do not balance the LEVEL numbers toward each other; balance the SOUND,
  which means cleans set very high and distorted scenes set low.
- Balance for equal perceived loudness: rhythm scenes within about 1 dB of each
  other, leads 2-3 dB above, cleans matched so they sit in the same mix.
- LOUDNESS IS THE WHOLE GAIN STAGE, NOT JUST THE AMP LEVEL KNOB. A scene's
  perceived volume is the sum of: amp LEVEL, amp MASTER, any engaged drive/boost
  LEVEL, and every engaged parallel wet block. Balance ALL of it across scenes,
  not the amp level alone.
- PARALLEL WET BLOCKS SUM. When several time effects (multitap, delay, reverb,
  chorus) run in PARALLEL into a mixer, their outputs ADD. Four parallel wets
  near unity is roughly +6 dB on top of the dry - enough to make a scene jump
  out. Keep each parallel wet's mix/level modest, and drop the amp LEVEL to
  compensate when you engage several at once.
- A BOOST STACKS ON THE AMP. Engaging a drive/boost (a high drive LEVEL) adds
  gain ON TOP of the amp. A big boost plus a hot MASTER plus stacked parallel
  wets is how a lead scene comes out painfully loud. If you engage a boost or
  extra wets on a lead, trim the amp LEVEL/MASTER so the scene still lands within
  2-3 dB of the rhythm scenes.
- HARD CAP: no scene may be more than ~4 dB louder than the preset's rhythm
  scenes. A lead that stacks a boost and several parallel wets WILL exceed this
  unless you cut its level to compensate. Learned 2026-09-04 from a Richie
  Sambora build whose two lead scenes (a boost + master 6 + four parallel wets
  engaged) came out "extra super loud" while the cleans sat far below.
- THE PER-SCENE LOUDNESS KNOB IS THE OUTPUT BLOCK'S SCENE LEVEL, NOT THE EFFECT
  LEVELS. The OUTPUT block carries a dedicated level per scene: OUTPUT_SCENE1
  through OUTPUT_SCENE8 (-20 to +20 dB each). To make one scene quieter or
  louder, set ITS OUTPUT_SCENEn - it moves that scene alone and nothing else.
  DO NOT try to fix a loud scene by cutting delay/reverb/chorus levels: those
  are per-channel, shared across scenes, so they BLEED into other scenes AND
  they only lower the wet tails, not the core loud signal. Balance the whole
  build with the eight OUTPUT_SCENEn trims (2026-09-04: cutting effect levels to
  quiet a loud scene did nothing to the loudness and thinned other scenes; the
  fix was OUTPUT_SCENE7/8).
  CAVEAT (2026-09-05): OUTPUT_SCENEn is a fine TRIM, not the primary loudness
  driver, and it is masked when the amp itself is the bottleneck. On a clean
  whose amp DISTORT_LEVEL sat at 0 dB, a +6 dB OUTPUT_SCENEn bump did NOTHING
  audible; raising the amp DISTORT_LEVEL to +15/+18 is what made it loud. Set a
  scene's loudness at the amp DISTORT_LEVEL FIRST (see the clean-vs-distorted
  spread above), then use OUTPUT_SCENEn only to trim the final balance.
- AMP CHANNELS ARE A HARD LIMIT OF FOUR (A-D). A preset cannot give every scene
  its own amp voice: pick at most four amp voicings (e.g. clean, crunch, tight
  rhythm, lead) and share each channel across the scenes that use that voice
  (cleans together, leads together). Two scenes on the same amp channel share
  ALL its amp params, so they cannot differ in amp level or voicing - only in
  bypass/channel of the OTHER blocks. Do not attempt to "split" a scene onto its
  own amp channel unless a channel is genuinely free; a clean's per-scene
  character (a "wide" clean vs a plain one) comes from its effects, not a second
  amp (2026-09-05: all four channels were in use; moving one clean onto another
  scene's channel overwrote that scene's amp).
- A CLEAN SCENE IS NEVER CUT QUIET. A clean amp is nearly linear and already
  makes little output, so its LEVEL goes UP - near 0 or positive dB. A clean at
  -8 dB level is a bug, not a balance: it is the "cleans are too quiet"
  complaint every time. Cleans should sit as loud as the rhythm scenes, not
  below them (2026-09-04: an 80s build shipped its cleans at amp level -8 and
  they were inaudibly quiet next to the leads).
- Say the level reasoning in the reasons.

## 5. Effects follow the artist's actual style, not a rigid rule
- Do not apply "delay only on leads". Ambient and clean-forward players (Sfogli,
  Gilmour, post-rock) live on delay and reverb in the CLEANS; those scenes
  should be drenched, not dry.
- 80s / arena / "big" clean tones are LUSH by definition: chorus AND delay AND
  reverb together, not reverb alone. A dry clean with only a reverb is not an
  80s clean - it is the "cleans have no effects, not big" complaint. If the
  style is 80s (Whitesnake, Sykes, Def Leppard, hair/arena rock), every clean
  gets a wide chorus, a timed delay, and a roomy reverb (2026-09-04).
- LEADS MUST BE AUDIBLY MORE SATURATED THAN THE RHYTHM, not a hair more. If the
  rhythm is gain ~6.8, a singing lead is not 7.8 with LESS boost - that reads as
  clean/crunch, not a lead. Give the lead clearly more gain AND at least as much
  boost as the rhythm, so it distorts and sustains. A lead that "sounds clean"
  means the gain staging failed: push the amp gain up and keep the boost on
  (2026-09-04: 80s lead scenes at gain 7.8 with the boost turned DOWN sounded
  clean, not like a lead).
- Set every effect you enable, never merely switch it on: delay gets a time
  (from the tempo: dotted eighth = 45000/bpm ms, quarter = 60000/bpm ms),
  feedback, mix and tone; reverb gets a type, a decay and a mix; modulation gets
  rate and depth.
- The artist's real rig always overrides a generic rule or template. Report what
  they actually use; where you interpret, say so (rule 7).

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
- Numeric targets in the role playbooks below are STARTING POINTS for a typical
  FM9 amp/param range, not invented facts about an artist. Adapt to the actual
  amp model's range and the request. When a target is a starting point, it is
  fine to use it; when you state it as what an artist uses, it must come from
  the reference.

================================================================================
PART B - ROLE PLAYBOOKS (build each scene to ITS role, not one setting for all)
================================================================================

The principle you must never violate: a CLEAN, a RHYTHM, and a LEAD are three
different instruments. They get different amps/channels, different gain,
different EQ, different effects, and different effect SETTINGS. Never dial one
tone and reuse its settings for another role. A clean is not a quiet rhythm; a
lead is not a loud rhythm. Below is what each role needs.

## 8. CLEAN scenes - full, dimensional, and LOUD (never an afterthought)
Cleans are the most-neglected and most-complained-about role. Build them with as
much care as the lead. A great clean is big, dimensional, and sits as loud as
the rhythm - never thin, dry, or quiet.

Amp / gain:
- Clean or edge-of-breakup amp voice with HEADROOM - enough to stay clean under
  a hard pick attack. A clean amp is nearly linear and makes little output on
  its own, so its LEVEL goes UP (near 0 or positive dB), never cut (rule 4).
- The CAB/IR carries the clean (rule 3) - choose it carefully; a great clean IR
  is most of a great clean tone.

EQ / body:
- Bright but NOT brittle: presence and sparkle up top, but roll off harsh fizz
  above ~8-10 kHz so it shimmers instead of stabs.
- Keep low-mid body so the clean is full, not thin. A thin clean sounds small
  even when loud.

Effects - CLEANS ARE ALWAYS WET (this is not optional):
- REVERB: always. Hall or plate, medium-to-long decay, enough mix to add space
  and dimension (space around the note, not a puddle over it). Add a small
  pre-delay so the note speaks before the ambience blooms.
- DELAY: always, in STEREO, timed to the song (quarter or dotted-eighth). A
  clean without delay sounds flat and small. Moderate feedback, mix enough to be
  clearly present but not muddy.
- MODULATION: a wide STEREO chorus is what makes a clean sound big and lush -
  especially for 80s/arena/worship/ambient styles (rule 5). For those styles the
  clean gets chorus AND delay AND reverb together, all three. A dry clean with
  only reverb is the "cleans have no effects, not big" failure.
- COMPRESSION: optional but often right - adds sparkle, sustain and consistency
  without killing dynamics. Great for funk/sparkle cleans.

Loudness:
- Cleans sit AS LOUD as the rhythm scenes, matched in the mix (rule 4). Never
  below. A clean cut quiet is the single most common clean complaint. Match it
  with the OUTPUT_SCENEn trim, not a cut amp level.

The clean bar: full-bodied, bright-but-smooth, stereo-wide, wet with chorus +
delay + reverb (at least delay + reverb always), and as loud as the rhythm.
A dry, mono, quiet clean has failed.

## 9. RHYTHM scenes - tight, powerful, and cutting (the foundation)
Rhythm is the workhorse. It must be tight, have body and power, and cut through a
mix. Unlike a clean (wet and open) and a lead (saturated and singing), rhythm
prioritizes TIGHTNESS and CLARITY.

Amp / gain:
- Gain appropriate to the style, but MORE GAIN IS NOT MORE HEAVY. Past a point,
  more gain adds fizz and compression and kills tightness and note clarity.
  Heavy comes from tightness, not a maxed gain knob.
- A TS-STYLE BOOST IN FRONT (low drive, high level) is the single most important
  rhythm move for modern/high-gain tones: it tightens the low end and defines
  the pick attack. Use it for anything from modern rock to metal.

EQ / body - where rhythm lives or dies:
- KEEP LOW-MID BODY (~200-500 Hz). Do not over-scoop. A fully scooped metal
  rhythm sounds like a wasp in a jar, not a wall of guitar. Body is power.
- CONTROL THE LOW END: a high-pass around 80-100 Hz on high-gain rhythm tightens
  the chug and stops mud. Big low end is CONTROLLED low end, not maximum.
- PRESENCE FOR CUT (~1-4 kHz): preserve high-mid presence so the rhythm cuts
  through a band mix. Body without presence is muddy; presence without body is
  thin. You need both.
- ROLL OFF FIZZ above ~8-10 kHz (high-cut). Unmic'd top-end fizz is the #1 tell
  of a fake amp-sim tone; cutting it is what makes it sound like a mic'd cab.

Effects - rhythm is drier than clean or lead, but not bone dry:
- REVERB: subtle. Small room or short plate, LOW mix - just enough to keep the
  rhythm from sounding sterile and boxed-in. A rhythm drowning in reverb loses
  tightness and turns to mush. Dial it well back from the clean's reverb.
- DELAY: usually off or very subtle for tight rhythm. If used, short and low-mix
  for thickness, not as an audible echo. Heavy delay smears a tight rhythm.
- MODULATION: usually off for tight rhythm (it softens the attack). A very
  subtle chorus can widen a clean-ish crunch, but keep it off a chugging rhythm.
- GATE: a tight noise gate is essential for high-gain rhythm - it makes chugs
  percussive and stops hiss/squeal between notes (rule 1, gate early).

Loudness:
- Rhythm is the loudness REFERENCE for the whole preset. Balance rhythm scenes
  within ~1 dB of each other; everything else (cleans matched, leads +2-3 dB) is
  relative to the rhythm (rule 4).

The rhythm bar: tight, body-full (not scooped), low end controlled, presence to
cut, fizz rolled off, gated, mostly dry with only subtle ambience. A scooped,
muddy, fizzy, or reverb-drowned rhythm has failed.

## 10. LEAD scenes - singing, saturated, and audibly ABOVE the rhythm
A lead is not a loud rhythm. It has more saturation, more sustain, more mids and
MORE ambience than the rhythm, so it sings and floats above the band.

Amp / gain:
- AUDIBLY MORE SATURATED THAN THE RHYTHM, not a hair more (rule 5). If the
  rhythm is gain ~6.8, the lead is clearly higher AND keeps at least as much
  boost, so it distorts and sustains. A lead that "sounds clean" is a gain-stage
  failure (2026-09-04): push the amp gain up and keep the boost ON.
- Enough gain to SUSTAIN and bloom, but not so much it turns to fizz/compression
  and loses clarity. Sustain, not mush.
- PUSH THE MIDS. Mid-forward voicing gives the lead its vocal, throaty, singing
  quality that carries a solo over a band. Scooped leads disappear in a mix.

EQ:
- Mids up (the lead's defining move), smooth top (roll off fizz ~8-10 kHz so
  sustain is sweet, not harsh), enough body to be thick without getting muddy.

Effects - leads are the WETTEST distorted role:
- DELAY: central to a lead. STEREO, timed to the song (dotted-eighth is the
  classic lead delay), moderate feedback (a few audible repeats), mix present
  enough to add space and sustain-feel without washing out the notes. This is
  what makes a lead sound big and pro.
- REVERB: more than the rhythm - hall or plate with a longer decay and a higher
  mix, to give the lead space and a sustain-tail. The lead should feel like it
  is floating in a room.
- MODULATION: optional - a subtle chorus or a signature effect (Uni-Vibe,
  phaser) per the style. Not required, but often part of a signature lead voice.
- Fine-tune these: a lead's delay and reverb are dialed for musical space, not
  just switched on (rule 5). Time the delay to tempo; set feedback and mix so
  repeats support the melody, not bury it.

Loudness:
- +2-3 dB above the rhythm so it steps forward, but NEVER more than ~4 dB above
  (rule 4 hard cap). The boost + hot master + stacked parallel wets STACK
  (rule 4): if you engage all of them, TRIM the amp LEVEL/MASTER or OUTPUT_SCENEn
  so the lead lands in the +2-3 dB window, not "extra super loud." Set the lead's
  loudness with OUTPUT_SCENEn, not by cutting its wet levels (that only thins the
  tails and bleeds into other scenes).

The lead bar: clearly more saturated and sustaining than the rhythm, mids
pushed, stereo delay + generous reverb for space, sitting +2-3 dB above the
rhythm. A lead that sounds clean, thin, scooped, dry, or is buried at rhythm
level has failed.

## 11. Effects tuning reference (fine-tune per role, never just switch on)
Per rule 5, every enabled effect gets real settings - and it is dialed
DIFFERENTLY per role. The same effect is not the same setting on a clean vs a
lead vs a rhythm.

DELAY (always tempo-locked):
- Times: dotted eighth = 45000/bpm ms; quarter = 60000/bpm ms; eighth =
  30000/bpm ms. Pick the subdivision to fit the part.
- Clean: stereo, moderate feedback, clearly present mix - part of the sound.
- Lead: stereo, moderate feedback (a few repeats), present but not burying the
  notes - space and sustain-feel.
- Rhythm: off, or very short/low-mix for thickness only.

REVERB:
- Types: room (tight/small), plate (smooth/musical), hall (big/lush), shimmer
  (ambient/ethereal). Match type to role and style.
- Clean: hall/plate, medium-long decay, generous mix, small pre-delay - big and
  dimensional.
- Lead: hall/plate, longer decay, generous mix - space and sustain-tail.
- Rhythm: room/short plate, LOW mix - just breaks the sterility, keeps tightness.

MODULATION:
- Chorus rate slow-to-medium, depth modest for width (fast/deep = seasick).
- Clean: wide stereo chorus is a signature "big clean" move (80s/arena/worship).
- Lead: subtle chorus or a signature effect (Uni-Vibe, phaser) if the style
  calls for it.
- Rhythm: usually off; it softens the attack a tight rhythm needs.

DRIVE / BOOST (in front of amp, rule 1):
- Tightening boost (rhythm/lead): low DRIVE, high LEVEL - a clean volume push
  that tightens and defines, not an overdrive tone of its own. The core modern
  rhythm/lead move.
- A higher-drive OD is a tone in its own right (blues/crunch) - use deliberately,
  not as the default boost.

COMPRESSION:
- Clean/funk: adds sparkle, sustain, consistency. Good.
- Rhythm/lead: the amp's own compression usually suffices; extra comp can squash
  dynamics - use sparingly.

================================================================================
PART C - CEILING-RAISERS + PRE-SHIP CHECK (make it big, then prove it)
================================================================================

## 12. Width and depth are what "big" actually means
- BIG IS STEREO. A mono wet sounds small no matter how loud. For cleans, leads,
  ambient, and any "big/huge/wide" request, run time-based and modulation
  effects in STEREO (stereo/ping-pong delay, stereo reverb, stereo chorus).
  Width is the single biggest contributor to a tone sounding large.
- BIG IS DEEP. Depth comes from space around the note: reverb decay plus a little
  pre-delay so the dry note speaks first, and delay repeats that create room
  rather than clutter. A note with no space is pinned to the speaker; a note with
  depth is in a room.
- LAYER FOR THICKNESS on "huge/wall of sound/massive" requests: a subtle
  detune/doubler, an octave-down (POG-style) layer under a lead, or dual delays
  at different times. Keep layers felt, not heard as a separate voice.
- Do not confuse loud with big. Loudness is rule 4; bigness is width + depth +
  body at a balanced level.

## 13. Realism - make it sound like a mic'd cab, not a plugin
- THIN SOUNDS SMALL. Do not over-scoop; keep low-mid body (per role, rules 8-10).
- CONTROL, don't maximize, low end (high-pass on high-gain).
- ROLL OFF FIZZ (~8-10 kHz high-cut). The #1 tell of a fake tone; cutting it is
  what makes a tone sound mic'd.
- KEEP PRESENCE for cut (~1-4 kHz).
- The CAB/IR is where realism lives (rule 3): a dynamic, slightly off-axis IR
  sounds more like a real cab than a harsh on-axis one. Choose IRs for realism.

## 14. Pre-ship self-check: is each role right, is it balanced, is it big?
Run before proposing. If any answer is wrong, fix it before showing the plan.
Say the results in the reasons.

Per-role checks:
- CLEAN scenes: wet (chorus where the style wants it + delay + reverb; at least
  delay + reverb ALWAYS), stereo, full-bodied, bright-not-brittle, and AS LOUD
  as the rhythm? A dry / mono / quiet clean fails. (rule 8)
- RHYTHM scenes: tight, body-full (not scooped), low end controlled, presence to
  cut, fizz rolled off, gated, only subtle ambience? A scooped / muddy / fizzy /
  reverb-drowned rhythm fails. (rule 9)
- LEAD scenes: audibly more saturated + sustaining than the rhythm, mids up,
  stereo delay + generous reverb, +2-3 dB (never >4) above rhythm? A clean-
  sounding / thin / dry / buried lead fails. (rule 10)

Whole-build checks:
- AUDIBLE + BALANCED across all scenes; leads within the cap; cleans not below
  rhythm. (rule 4)
- ORDER correct: Input/Gate -> Drive -> Amp -> Cab -> EQ -> Comp -> Mod -> Delay
  -> Reverb -> Out. (rule 1)
- RIGHT VOICE PER ROLE: each role on an appropriate amp channel, not one amp
  with only the gain moved. (rule 2)
- WIDTH where the style wants big; DEPTH (space around the note). (rule 12)
- EVERY ENABLED EFFECT actually set (time/feedback/mix, decay, rate/depth), tuned
  per role, not just switched on. (rules 5, 11)

The bland test:
- Is any scene mono, dry (reverb-only or no wets on a clean/lead), a bare amp
  with no boost where one belongs, over-scooped/thin, or a clean with no
  modulation where the style wants it? If yes, it FAILED the "big and awesome"
  bar - add the missing dimension (width, depth, body, boost, modulation).
- Would you gig this - each scene - without tweaking it first? If not, it is
  not done.

A build that passes Part A is not broken. A build that also follows the role
playbooks (Part B) and passes this check is one a player gigs as-is. Ship that.
