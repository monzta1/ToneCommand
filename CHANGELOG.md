# Changelog

Notable changes to ToneCommand. Dates are UTC.

## Unreleased

### Added
- **Compose a preset from parts of other presets.** Clone a whole tone into a
  new slot, then pull the delay from one preset, the reverb from another, the
  amp from a third: "copy BT Marco Sfogli into slot 21, but take the delay
  from <A> and the reverb from <B>". Every source is read first, then the new
  preset is assembled and stored once, respecting the store whitelist. This is
  a better path to an artist tone than guessing parameters from scratch, and
  it came straight out of the Marco Sfogli experiment, where the pro preset's
  clean delay was a full stereo setup no guess would reproduce. Underneath is
  copy-effects, which lifts named blocks (delay, reverb, any family) from one
  reference preset onto the current build wire for wire. Both copy settings and
  bypass; the signal-chain order is not moved yet (owner, 2026-09-04).

### Changed
- **Builds match the amp to each scene's role, and spend effort where the
  tone actually lives.** The planner picked one amp family and moved the gain
  knob from clean to lead. It now puts a clean-voiced amp on clean scenes and
  a high-gain amp on lead/rhythm scenes (on their own channels), and weights
  its voicing by role: a clean signal is nearly linear so the cabinet carries
  it, while distortion is the amp's to make so a lead's gain structure and
  sustain carry the feel and no cab can fake it. Learned by comparing a blind
  ToneCommand build to a pro artist preset, which used a different amp per
  scene role under captured IRs (owner, 2026-09-04).
- **Sending shows a progress bar, not a wall of actions.** The send used to
  stream every one of a hundred-plus writes past the player ("Sending 113 of
  129: AMP 1 DISTORT_MASTER"). It now shows a filling bar and a percentage,
  with a "show details" toggle that reveals the per-action log for when
  something looks wrong (owner, 2026-09-04).

### Fixed
- **Scene-aware copy now lands each effect on the right scene, not the wrong
  one.** A channel-for-channel copy is scene-blind: two presets map scenes to
  channels differently, so copying an artist tone put its lead delay on the
  clean scene. The scene-aware path copies what the source did on scene N onto
  the target's scene N. The first cut had a subtle bug hardware caught: FM9
  parameters live per channel, not per scene, so when several target scenes
  shared a channel a per-scene write loop had each later scene overwrite the
  earlier one, and a two-scene copy came back 10/10 instead of 10/20. The fix
  is the only decomposition the device's data model allows: copy the channel
  parameters once each, then copy the per-scene channel and bypass assignments.
  Hardware-confirmed, with a CI regression guard that models per-scene channels
  (the sim cannot). GitHub #48 (owner, 2026-09-04).

## 0.9.0 (2026-09-04)

### Fixed
- **From-empty builds no longer abort halfway.** Building into an empty slot
  laid the starting chain, then the first block-add read back to verify and
  false-failed a block that had actually landed, so the fail-fast abandoned
  the rest ("Sent 0 of 1"). Two causes: the read could race the write and see
  the pre-splice grid, and some blocks report a transient type id right after
  placement (a gate reads back as id 18 for a beat before settling to its
  real 146), which an exact-id check rejected. The block-add now polls briefly
  for the exact id, then confirms by what is actually provable: a non-shunt
  block occupies the cell we spliced into and it is not one of the blocks we
  slid over, so it can only be the one we placed, with the signal-path check
  still proving nothing broke. Never a blind pass. Verified on hardware across
  gate, drive and full builds, repeatedly (owner, 2026-09-03).
- **Long preset names no longer fail the whole build.** A generated name at
  the FM9's length limit came back one character short (the field holds one
  fewer than the 32 we budget), and the exact-match name check failed the
  rename and, with it, the build. The rename now accepts the device's own
  truncation of the name it was given (owner, 2026-09-03).

### Changed
- **The main workflow now speaks like a player, not a control protocol.**
  Waiting no longer mentions a server or reports silence in seconds. Plans
  no longer display AI backend or model identifiers. The review rail now says
  WHAT WILL CHANGE, READY CHECK, and IF YOU CHANGE YOUR MIND instead of blast
  radius, preflight, and reversibility. Internal validation messages are
  translated into safe next steps, routing warnings describe the audible
  consequence without grid terminology, and send failures keep their exact
  detail in Activity while the workflow gives a calm recovery step. Advanced
  AI address and model fields are no longer exposed (owner, 2026-09-03).
- **Empty slots now build themselves when a tone needs one.** The EMPTY SLOT
  panel and PROPOSE STARTING CHAIN button are gone. Ask for a tone while an
  empty slot is loaded and ToneCommand creates the basic signal path inside
  the reviewed send, then continues voicing the requested sound. The plan
  says this will happen before anything reaches the FM9. The same guarded,
  read-back-checked path still performs every change (owner, 2026-09-03).
- **One request box for every kind of tone request.** Describe a sound, ask
  for a whole rig, request a small adjustment, or paste a link in the same
  place. ToneCommand now recognizes what was entered and chooses the right
  path itself. The DESCRIBE, SOURCE, and EMPTY SLOT choices are gone, along
  with the second source form. A direct request starts its plan immediately;
  if one important detail is missing, the answer continues in the same
  conversation (owner, 2026-09-03).
- **One prompt, one window: a build never times out for being large.**
  A whole-rig ask and a one-block tweak arrive through the same prompt, and
  the player never chose between them, yet the interactive path used a short
  planner window while the build path used a long one. A big multi-scene
  request through the prompt could fail with an internal-sounding timeout
  while the same request through the build flow succeeded. Every plan now
  runs under the build-sized window; the streaming heartbeat, not a short
  deadline, tells a long build from a hang. And when a build genuinely does
  not come together, the conversation shows a plain next step ("that took
  too long, give it another go, or ask for a little less at once") instead
  of the raw transport or timeout text. No planner internals reach the
  player (owner, 2026-09-03).

### Added
- **COPY a whole conversation.** A COPY button in the chat controls puts
  the entire exchange on the clipboard as plain text, each turn labelled
  the way the page shows it (YOU, TONECOMMAND with its model, and system
  notes), so a snag can be pasted straight into a help thread without
  retyping (owner, 2026-09-03).
- **A pick-what-to-install plan for acquired presets.** When a search or a
  Gift of Tone fetch turns up more than one preset, ToneCommand no longer
  fires a blunt confirm dialog. It opens the Storage drawer with every
  preset listed and checked by default, each with an editable destination
  slot (auto-numbered from any "to preset N" you said) and a note of what
  that slot currently holds, plus a single toggle for the pack's cabs. A
  live line spells out exactly what WRITE will do before you press it: how
  many presets, to which slots, which one loads first. Uncheck anything
  you do not want; only the checked rows are written (owner, 2026-09-03).

### Changed
- **Stripped the verbosity.** Explanation was stacked on explanation
  across the page, overwhelming for a first-timer (owner, 2026-09-03).
  Every always-visible hint was cut to its essence, with the full detail
  moved into a hover title where it still helps: the Storage drawer's
  three paragraphs became short lines, the store-slots help went from ~90
  words to one, the source, recipe, design, compare, diagnostics and grid
  hints all shrank, and the loaded-slot and slot-count messages are
  single lines now. Safety warnings (flash writes, "no copy kept") stay,
  just tighter. Nothing about behavior changed.

### Fixed
- **Filler, plurals and typos no longer break a local search.** "find the
  luke TONES and load THEM ON my SYSTEM", and even "IND the luke tones"
  with a dropped letter, were matching nothing while the bare "luke"
  worked: every extra word was a required search term with no file to
  match. The local search now ranks files by how many query words the
  name answers to and keeps the best, so a pronoun, a location word or a
  typo simply does not score instead of sinking the whole search. A real
  artist name that is not on disk still finds nothing; it ranks, it does
  not guess. Asking for two artists at once now returns both (owner,
  2026-09-03).
- **The Inspector no longer garbles amp/cab names, and EXPANDs for room.**
  The amp/cab pair and knob grids were laid out for a full-width page, so
  in the 356px Inspector rail the amp value overflowed into the cabinet
  and the cab's description wrapped one word per line (owner,
  2026-09-03). They stack cleanly in the rail now, and a new EXPAND button
  floats the Inspector over the work canvas: amp and cab side by side with
  the full description readable, the whole tone stack and effects in
  multiple columns, every slider visible at once.

### Added
- **Installing a file is a review-and-send flow you name (#42).**
  Dropping a preset or bundle now shows a card with an editable NAME
  field (the name the slot will carry, footer refolded so a real device
  accepts it), a destination picker, and a REVIEW & SEND button; sending
  shows a live "transmitting, reading back" line and a loud DONE/ FAILED
  announcement, and on success every slot dropdown reloads with the new
  name at once. The old two-button layout (a generic STORE that quietly
  acted on the edit buffer, beside the file's own install) was the trap
  that made a bundle look stored when it was not (owner, 2026-09-03).
- **Purchased .fasBundle packs install, cabs included, where the vendor
  says (#42).** An FM9-Edit .fasBundle is a zip holding a Bundle-Map
  that pins every cab to the user-cab bank and number the preset
  references. Drop one on the Storage drawer and the preset plus each IR
  appear with those destinations fixed, so nothing is left to the player
  to get wrong. Verified against real purchased BoutiqueTones packs (six
  presets, thirty vendor-pinned cab destinations, all parsing). Bank
  addressing on the wire is not assumed: the destination is read-probed
  first and the write uses only an addressing the device itself answered
  for. Bundles for other Fractal devices are refused by device id.
- **IRs install to the slots the artist filed them for (#42 phase 4).**
  When a fetched bundle ships user-cab IRs, they appear beside the
  presets with their destination already set from Fractal's own U{n}
  export naming: the user-cab slot the presets actually reference, which
  is the step players get wrong by hand. The cab envelope
  (0x7A/0x7B/0x7C) was verified against a real artist export (Wes Hauch,
  GoT 2023); artists export IRs under whatever device their editor had,
  so installs rewrite the model byte with checksums recomputed. IR
  writes have their own whitelist (TONECOMMAND_CAB_SLOTS, disabled by
  default because user cabs are user property), their own transport
  guard, and are verified by reading the cab back byte-identical.
  FM9-Edit .fasBundle files are named as not-yet-supported instead of
  vanishing. The write direction, model rewrite and slot addressing are
  hardware-unverified until the first live install, and every surface
  says so.
- **"Get me the Periphery tones from Gift of Tone" now works as a
  sentence (#42).** A named source in the COMMAND box routes to a fetch
  instead of the tone planner, which would have built an imitation of a
  preset whose real version is a free download. The official Gift of
  Tone catalog is matched deterministically (no model in the loop,
  nothing to hallucinate; an unmatched ask lists recent gifts instead of
  guessing), the bundle is downloaded once, every FM9 preset inside is
  validated by the same parser as a dropped file, wrong-device variants
  are skipped with reasons, and the results land in the Storage drawer
  with a slot picker each. Flash writes still go one at a time through
  the whitelist, the gig lock, the confirmation and the read-back check.
- **Install preset files (#42).** Drop a .syx from Gift of Tone,
  Axe-Change or a friend into the Storage drawer and it lands in a
  whitelisted slot. The parser trusts nothing: every frame checksummed,
  the documented 0x77/0x78/0x79 envelope enforced, the model byte
  matched (a file for another Fractal device is refused by that device's
  name), the embedded preset name decoded for the preview. Installing is
  the official editor's own Ghidra-decoded recipe: the file's frames
  verbatim, header retargeted, footer untouched, sent through a separate
  transport guard that admits only the dump family, so the ordinary send
  surface did not widen by one function. The store whitelist and gig
  lock apply exactly as for STORE, and done is claimed only after the
  slot's name reads back and matches. Validated against the real
  Periphery Gift of Tone 2024 files (all three parse; their FM3 and
  Axe-Fx III variants are refused by name). The host-to-device dump
  direction is not yet hardware-proven anywhere, this project included:
  the first live install is the verification, and until then the result
  copy and the simulator both say so.
- **The first-class build standard.** Identity builds (a player, band,
  song, style, or multi-scene rig) are now held to a written standard in
  the planner prompt: voice the full amp stack in every scene, choose the
  cabinet deliberately, set tempo and compute delay times from it, give
  every enabled effect real values, balance scene levels for the gig, and
  consider Pedal 2, with depth never licensing invented parameters. Small
  adjustments are exempt: "a bit more presence" still changes one thing.
  Measured on the same Tom Petty request that prompted it: 69 actions
  with tempo-synced delays and a voiced compressor, against the vanilla
  handful before. The Plan stage also grew a DEPTH card that names what a
  build left untouched, so laziness is visible before anything is armed.
- **The AI picker is a question, not a form.** Settings opens on WHO PLANS
  YOUR TONES: named cards (Claude subscription, ChatGPT subscription,
  ChatGPT API, Gemini, Grok API, DeepSeek, Kimi, Local model, OpenRouter,
  Automatic), each stating its cost and its state: READY, NEEDS A KEY with
  a GET A KEY link to the right page, NEEDS SETUP, or NOT INSTALLED. A
  READY card takes effect on the click. Backend, service address and model
  id moved under ADVANCED; the words "backend" and "endpoint" no longer
  appear on the main path.
- **The Local model card finds your local server.** It probes LM Studio's
  and Ollama's ports and uses whichever is answering, instead of
  hardcoding one and sending Ollama owners into ADVANCED to type an
  address.
- **Planner errors name the service, not the protocol.** A Gemini quota
  failure now reads "Gemini [http_status] 429", not "openai [...]".
- **Models that emit bare actions still plan.** Gemini answered an
  8-scene build with one JSON object per action and no {summary, actions}
  envelope; the extractor now gathers action-shaped output into a plan
  instead of calling it empty. Every action still passes validation.

### Fixed (redesign follow-ups, all owner-reported same day)
- The Confirm acknowledgement no longer unchecks itself: the five-second
  poll was redrawing the stage and wiping the checkbox faster than a
  person could arm.
- The conversation scrolls back: flex-end pinned overflow above the
  container's top edge where no scrollbar reaches, and the busy tick's
  rewrites killed scroll gestures. A collapsing spacer seats short
  exchanges low, rewrites pause while reading back, and a tall AGREED
  card opens at its top with scenes in two columns.
- The Inspector names blocks the way a player reads them (AMP, not
  DISTORT), scrolls to the right section, and the impact rail carries a
  MANUAL CONTROLS card with an OPEN AMP &amp; CAB shortcut.
- Every settings field has a visible label; the address label names the
  service it holds.
- **The desktop control surface.** The page is no longer a long document
  with tabs: it is a fixed five-layer console built to
  docs/UI-REDESIGN-SPEC.md. A hardware bar names the FM9, the preset, and
  whether the edit buffer is modified; a five-stage rail walks REQUEST,
  PLAN, REVIEW, CONFIRM, SEND; scenes and the live signal path stay on
  screen through every stage; a command shelf pins UNDO and opens the
  Diagnostics, Library, Storage, Activity and Settings drawers. SEND is
  reserved for hardware: the composer says GENERATE PLAN, Review is a
  filterable change table with the blast radius and preflight beside it,
  and Confirm is a full stage with a facts matrix, an acknowledgement, ARM
  SEND, and an eight-second SEND TO FM9 window that Esc or any target
  change disarms. Transmission reports SNAPSHOTTING through COMPLETE with
  verified counts, ends at EARS: PENDING, and a partial failure is never
  painted as success. Manual control opens as an Inspector from the signal
  chain; storing is STORE PRESET with erase behind a danger zone; below
  1180px the page refuses rather than compressing the send workflow onto
  a phone. Every existing capability kept its element and its handler;
  they moved house. All 1024 tests pass, with the tab-era pins rewritten
  against the stage rail.
- **The COMMAND console says who will answer, before you ask.** A quiet
  line at the top of DESIGN WITH AI reads "Planning with Gemini,
  models/gemini-3.5-flash", resolved server-side the same way the planner
  resolves its first candidate; clicking it opens the AI settings. It turns
  amber with the reason when the chosen backend cannot actually run. The
  backend used to introduce itself only on the finished plan, minutes after
  the sentence went in.
- **Gemini, Grok, DeepSeek and Kimi are one-click services in the AI
  settings panel.** Each chip fills in the address, says where its key comes
  from and what it costs, and lists real models the moment a key is saved.
  Prompted by Fractal FB community feedback (Martin White): he was already
  building tones with Gemini by hand, and the word Gemini appeared nowhere a
  chooser could find it. The backend dropdown now reads "ChatGPT, Gemini, or
  another service you choose", and the gear tooltip names the actual service
  in effect instead of "ChatGPT or other".

### Changed
- **The README is a page you can finish.** Community feedback said it was
  huge, and it was: 792 lines. It is now ~200, and everything it dropped
  moved rather than died: docs/INTERFACE.md, docs/AI-BACKENDS.md,
  docs/SETUP.md, docs/PROTOCOL-CONTRIBUTIONS.md and docs/CREDITS.md, all
  linked from a documentation table.

### Fixed
- **Google's product line is no longer offered as tone planners.** A fresh
  Gemini key listed video (veo), music (lyria), image (nano-banana),
  robotics, live-translation and browser-driving models beside the real
  ones, and reverse-alphabetical ordering both sorted veo FIRST and
  auto-saved it as the model. The filter now knows those families, the
  maintained "-latest" aliases lead the list, and the exact listing that
  bit is pinned in a test.
- **Each AI service now keeps its own key and model.** The named services
  behind the endpoint backend shared one storage slot, so clicking the
  Gemini chip showed ChatGPT's model in the box, and saving a Gemini key
  silently replaced the ChatGPT one ("my key vanished"). Both reported by
  the owner within minutes of the chips shipping. Keys and models are now
  stored per service address, chips swap in their own service's state, the
  models probe never sends one service's key to another, and old settings
  files migrate on their next save. Saving a key for a hosted service with
  no model picked now also fills the model in from the service's own list
  at save time, closing the trap where the planner sent the "local" default
  to an endpoint that 404s it.
- **Changing presets on the front panel no longer makes the rig cycle
  through all eight scenes.** The page was requesting the blast-radius map
  on every preset change, and the GET behind it walked every scene to read
  channel layouts, so browsing presets from the floor had the rig audibly
  stepping through scenes on its own. The sweep now lives behind
  POST /api/shared/sweep and runs only when a plan is on screen and needs
  the hints, announced in the log before the scene-stepping starts. GIG
  MODE refuses it outright, like the health scan. The plan renders
  immediately; hints fill in when the map lands.
- **The cached blast-radius map is invalidated when a transmit changes it**:
  a channel write or a new block cleared the cache, where before a stale
  map could keep describing the old scene-to-channel layout.

## 0.8.0 (2026-09-02)

One wait experience, everywhere. The COMMAND box learned to count seconds,
listen for a heartbeat and offer a way out months before the rest of the app
did; every other path that could run for more than a few seconds still hid
behind a frozen line of text. This release moves all of them onto the same
machinery, and makes STOP mean stop.

### Added
- **The claude CLI backend streams.** Plans stream their action count and
  chat streams its words through `--output-format stream-json`, so the
  "31 changes written" counter finally fires on the zero-configuration
  default install instead of only behind an OpenAI-compatible router. The
  wire format was verified against the real CLI, not assumed.
- **STOP stops the backend.** Abandoning a plan, chat, build or source read
  kills the planner subprocess on the server instead of leaving it burning
  for minutes while holding the settings lock. A request that does have to
  wait behind an earlier one now says QUEUED instead of pretending to work.
- **BUILD FROM A SOURCE streams.** Reading narrates its stages off the wire
  (fetching, downloading audio, the first-run whisper model, transcribing,
  extracting) with an elapsed count and STOP; building shows the same
  changes-written counter as the COMMAND box. Both used to be a static line
  over minutes of work, the exact failure the plan stream was built to end.
- **FIX IT goes through the streaming planner**, with the banner, the count
  and STOP, instead of a bare ASKING... over a multi-minute call.
- **The preset scan counts.** Reading all 512 slot names is about fifteen
  seconds of MIDI; the popover, RESCAN and NAMES now count n/512 through it
  instead of showing "nothing matches" over an empty list, which read as
  "your unit is empty".
- **The health scan names the scene it is standing on**, so the noises the
  rig makes during a scan are narrated rather than left unexplained, and the
  button counts SCENE n/8.
- **GIG MODE is on the page.** A header pill shows the performance lockout
  and toggles it; it used to exist only as an environment variable and an
  API, so the page looked normal while every control failed one refusal at a
  time, and the refusal then told a guitarist to POST JSON.
- The blast-radius sweep says so: mapping which scenes share channels steps
  the rig through all eight scenes audibly, and the log now names that read
  when it happens.
- **The LINK pill tracks the cable, both ways, in about a second.** The
  server keeps one CoreMIDI client with a real notify callback on a runloop
  thread, which is the thing that actually keeps a macOS process's view of
  the MIDI bus alive (two earlier fixes for this are recorded, disproven,
  in KNOWN_QUIRKS), and `GET /api/link/stream` pushes presence changes to
  the page the moment they happen. Verified across six live plug/unplug
  cycles on real hardware.

### Fixed
- **A build aimed at an empty slot lays its own foundations.** A 135-action
  plan used to halt at "ADD amp" on a freshly erased slot and tell the
  player to go and press BUILD A STARTING CHAIN themselves: the tool knew
  the problem, knew the remedy, owned the code for it, and handed the work
  back. A transmit containing add_block now builds the starting chain
  itself when the loaded slot is empty (announced on the plan card before
  confirmation, reported as its own row in the results), and an add for a
  block already present counts as satisfied instead of halting everything
  after it.
- **Erasing is one confirmation now; the typing test is retired.** The
  typed-name echo refused legitimate attempts over invisible double
  spaces, then over a machine-built title, then got fed the slot number,
  all in one evening. What survives is the part that protects: ERASE only
  arms once the slot's name has been read and shown, the single dialog
  names the slot and exactly what it holds, and the page sends the name it
  displayed for the server to match against flash, so a slot that changed
  since it was shown still refuses. API callers keep the name contract,
  spacing and case forgiven, and a typed slot number gets a reply naming
  the actual ask instead of a bare refusal.
- **Every slot label now leads with the number on your unit.** The header
  pill said 159 while every label below said "158 (FM9-Edit 159)", so the
  app looked like it disagreed with itself about which preset was loaded.
  Labels are "159 (wire 158)" everywhere now: the front-panel number
  first, the MIDI wire number named for what it is in the bracket. One
  function owns the format, so nothing can drift back. The SAVE dropdown
  also fills its names right after startup instead of saying "name not
  read" until NAMES was pressed.
- **The SAVE panel contradicted its own dropdown after an unsaved build.**
  The "Loaded:" line printed the edit buffer's name as though it were the
  slot's, directly above a dropdown showing what flash actually holds, and
  the two read as mismatching data. They are two true facts about two
  different things; when they differ the panel now names both and says
  which is which: what the slot holds, what your unsaved edits are called,
  and that SAVE writes the second over the first.
- **A refused action was missing from the live transmit count.** The
  validation branch skipped the progress callback, so the SENDING counter
  stuck at n-1 of N while the final banner said otherwise. Found by running
  the stream against the real server, not by reading the code, which had
  looked fine. Refusals now count as failed steps.
- **ERASE refused legitimate attempts and looked broken.** The typed-name
  confirmation demanded an exact match against names that carry internal
  double spaces the eye cannot see and machine-built titles nobody retypes
  from memory; two real attempts in a row were refused, and the refusal
  landed only in the LOG panel, far from the button. Spacing runs and case
  are forgiven now (the name itself is not), refusals are logged
  server-side, and both the refusal and the success are announced in the
  strip. (The typing itself was retired later the same evening; see the
  one-confirmation entry above.)
- **A failed action was pointed at, not named.** "1 did not apply, marked
  above" left the player hunting through a hundred folded cards, twice in
  one evening. The outcome banner now names each failure with its reason,
  the card list opens itself and scrolls to the first failed card, and the
  server logs every refused action so a failure can be diagnosed without
  asking the player to read their browser back.
- **SHOW LOG sometimes needed several presses.** The working strip rebuilt
  its entire HTML every second, so the button being pressed was destroyed
  between mousedown and mouseup and the click fell into the gap. The strip
  is built once now and only its text updates.
- **The strip vanished at the finish, so completion looked like nothing.**
  It now holds the verdict for a few seconds, in the one place that cannot
  be scrolled away from: DONE in green with the count (and the stored slot
  when one was written), partial sends in amber, failures in red, and
  BUILD COMPLETE when a plan lands. A click dismisses it early.
- **A finished build looked like nothing happening.** The completion note
  landed in the chat transcript while the page scrolled you to the plan
  panel, so the one line saying "the build worked, TRANSMIT is next" sat
  exactly where you no longer were. The plan panel now opens with its own
  verdict strip: how many changes, that nothing has been sent, that
  TRANSMIT is the next step, and the truth about UNDO for store plans.
- **The preset dropdown kept the overwritten preset's name after a stored
  plan.** The slot-name cache was only ever invalidated by RESCAN, NAMES,
  rename and erase; a store inside a transmitted plan never told it. The
  store result already carries the slot's new name, so the cache entry is
  now corrected in place (no rescan) and the page re-pulls its lists after
  any transmit that stored. The SAVE button's full rescan-after-save is
  gone for the same reason: it spent seconds of MIDI to learn a name the
  store result had already delivered.
- **The transmit banner lied after a stored plan.** "Your presets are
  untouched; UNDO covers what landed" was shown after a plan whose store had
  just overwritten a flash slot, false on both counts and caught live on the
  first real build through the new pipeline. The outcome copy now checks
  whether a store landed and names the overwritten slot when one did.
- **Gig mode could audibly walk all eight scenes mid-song.** The shared-
  channel sweep ran automatically when the preset changed and was not gig
  gated, so a front-panel preset change during a set had the tool stepping
  scenes while someone played through it. It now refuses during gig mode and
  answers from cache only.
- HOLD A and HOLD B stayed dead for the rest of the session after any undo
  or recall: the recall disabled all five buttons and the refresh only ever
  re-enabled three.
- UNDO and RECALL say UNDOING.../RECALLING... while a forty-value restore
  runs; the preset pill shows a busy state while the unit switches.

Recipe sharing stops being code and starts being a thing that exists. The
worker and schema had been written and tested since 0.4.x and never deployed,
so the tone database existed as source and as nothing else: every recipe
anybody wrote went into the local outbox and stayed there.

### Added
- **The sharing service is live**, on Cloudflare Workers and D1. It holds an
  inbox and a counter and never content: recipes live in this repository's
  `recipes/` folder. That split decides the failure mode. If the worker is
  down, browsing and using recipes still work, only submission and ranking
  pause, and the client holds both until it returns. Nothing anybody writes
  depends on it being up.
- **`AUTO_PUBLISH`**, off by default. On, a submission is committed straight
  into `recipes/` and is live immediately, with no human step. Every
  submission is recorded in D1 either way, so it is one flag to undo with
  nothing lost. Be clear-eyed about what it means: `/submit` is
  unauthenticated, so with it on, anyone who can reach the worker can write a
  file into a public repository. That is a deliberate choice while there are
  no users rather than an oversight.
- **A note when a recipe was made on different firmware.** Recipes name models
  rather than numbering them, so a step resolves through the loading rig's own
  roster and a model that does not exist there is refused rather than becoming
  its neighbour. That covers the structural risk and not the audible one:
  Fractal revises voicings between releases, and `tested_firmware` was being
  recorded and shown to nobody. The plan now says so before you transmit.
- `service/wrangler.toml`, which did not exist, so there was nothing to deploy
  with.

### Fixed
- **The app could not find the service the docs told you to configure.**
  `share.endpoint()` read only `os.environ`, while the planner and the store
  whitelist both fall back to `.env`. So the documented setup left sharing
  silently dark: no endpoint, recipes queueing forever, nothing anywhere
  saying why. A configuration that fails closed AND says nothing is the worst
  of both.
- **A submitted recipe could carry anything.** The validator checked the
  envelope and never looked inside a step, so `steps: [1,2,3]` passed, and
  publishing writes the whole body, so any invented top-level key was
  preserved verbatim into the repository. On an unauthenticated endpoint with
  auto-publish on, that is "anyone may write arbitrary JSON into a public
  repo". Now: known keys only, every step an object whose kind is a real
  action, no invented keys inside steps, text bounded. `store` is refused
  outright, being the one action that writes to flash.
- Publishing refuses to overwrite. Not moderation, integrity: without it
  anyone could post a recipe named after a curated tone and silently replace
  it.
- The suite no longer reads the developer's real `.env` when testing sharing.
  The `.env` fallback leaked within a minute of being added, into a test
  asserting sharing was local only.

## 0.6.1 (2026-08-31)

### Fixed
- **The simulator let a discrete write of zero land on an enum.** Hardware
  never does: sub 09 carrying a zero value IS the zeroed GET, and it reads
  rather than writes for EVERY parameter, not only the continuous ones. The
  proof was already in `device.set_param_ordinal`, which sends ordinal 0 as a
  CONTINUOUS 0.0 precisely because the discrete path cannot carry it.
- 0.6.0 shipped the narrower guard, taken from #37 while merging #35 on the
  reasoning that it protected a legitimate discrete write of ordinal 0. There
  is no such write. Narrowing by parameter kind invented a distinction the
  device does not make, and left the simulator MORE permissive than the
  hardware, which is the wrong direction for a test double: code doing a
  discrete zero would have passed here and silently done nothing on the rig.
  Reported by @bschmalz81401 on #37.
- `test_zeroed_get_is_noop` now stands the settle window down. It had been
  passing for a reason unrelated to what it claimed: the window served the
  read from the pre-write snapshot while the live buffer had already been
  zeroed, so the damage was hidden on any machine fast enough. It failed only
  on CI. With no window there is nowhere for a bad write to hide, and a
  companion test now covers the enum case the old guard got wrong.

## 0.6.0 (2026-08-31)

Four things the tool could not do at all before: splice a block into a packed
chain, build into an empty slot without a terminal, erase a preset slot, and
rename one. Between them they close the last of the "you have to go and do
that part on the unit" gaps in preset structure.


### Added (renaming a slot, 2026-08-30)
- **A stored preset can be renamed from the app.** Not a text edit: the FM9
  keeps the name inside the preset, so renaming means selecting it, setting
  the name and storing the whole preset back. That makes it a flash write, and
  it carries the store whitelist, the gig gate, the select-landed check and
  the reload verification like anything else that writes. The slot is selected
  fresh first, so the store puts that preset back under a new name rather than
  baking in whatever edit buffer happened to be loaded.
- No `FM9AI-` prefix. `run_action` forces one on renames the planner proposes,
  so a tool-built preset is identifiable; a name the owner typed is theirs.

### Added (erasing a slot, 2026-08-30)
- **A preset slot can be erased from the app.** The second irreversible
  operation here, and the only one that destroys rather than overwrites: a
  store replaces a preset with the one you are holding, this replaces it with
  nothing.
- An empty slot is not "a preset with no blocks". The FM9 marks one in its
  NAME field, `"<EMPTY>"` over the first 8 bytes with the tail of the old name
  left as a ghost (finding 14), so all three parts are written: the grid is
  emptied, the eight scene names are blanked, and the marker goes into the
  name. A slot with an empty grid and its old name is not empty to the device,
  to FM9-Edit, or to `first_empty_slot`.
- Believed only after a reload. Finding 16's lesson applies to anything stored:
  an incomplete write reads healthy immediately, survives the store, and is
  found undone once the preset reloads, so the verification selects away and
  back before reporting. A clear that did not take says the preset may be
  damaged rather than cleared, because half-erased is worse than either end.
- Gated like nothing else in the product: the store whitelist (enforced by
  `store_preset` itself rather than re-implemented), gig mode, a select that
  must land where it was aimed, a confirmation naming the preset, and the name
  typed back by hand. The wire number and the number every screen shows differ
  by one, and a clear aimed one slot off cannot be taken back.
- The button is offered only for a slot whose name has actually been read.
  "Erase" over an unknown name is an invitation to destroy something nobody
  looked at.


### Added (empty slots, 2026-08-30)
- **Build a starting chain into an empty slot from the app** (#36). An empty
  FM9 slot has no grid cells at all, not even pass-through cells, so add_block
  has nothing to replace and the new splice has nothing to displace: both
  refuse, correctly, and the only way forward was a terminal. The builder now
  lives in `fm9/scratch_build.py`, which shipped code can import, and
  `tools/build_from_scratch.py` is a thin CLI over the same function rather
  than a second copy of a hardware sequence. An EMPTY SLOT panel appears when
  the loaded slot has no blocks, and the refusal from add_block points at the
  button instead of at a script.
- Unchanged: it only ever lands on a slot the device itself reports as
  `<EMPTY>`, it takes no force flag, gig mode refuses it, and nothing is
  stored, so the slot keeps reading `<EMPTY>` until the owner saves it.

### Fixed (server lifetime, 2026-08-30)
- A route that wrapped `get_fm9()` in `with` took the whole server process
  down, with no traceback and nothing in the log. The handle is already open,
  so re-entering it reopens a MIDI port on an endpoint that is already held;
  every other route uses the device without a context manager. Found on
  hardware, because the simulator does not model it.


### Added (splice in the planner, 2026-08-24)
- `add_block` splices when no free pass-through cell exists, instead of
  refusing. That refusal is what real presets hit, because none keep a spare
  cell before the amp (issue #10, decided as option 2). It displaces
  neighbours right, redraws the span, and proves a live Input-to-Output path
  before reporting success.
- The consequences are attached to the PLAN, not discovered at apply time,
  and the two kinds are kept apart: re-selecting the preset puts the slid
  blocks back, while nothing puts a spent pass-through cell back on its own,
  since shunts cannot be re-inserted. The plan card states each separately,
  the one-way step is styled differently and prefixed ONE WAY, and TRANSMIT
  asks about it in its own confirmation. One approval covering both with
  nothing to tell them apart is not informed consent.
- The one-way wording is the one hardware supports, which is not the one it
  started as. The first version said the spent cell does not come back "even
  after re-selecting the preset"; re-selecting reloads from flash, so it
  does. What is actually one-way is that nothing can put that cell back on
  its own: the only route is discarding the whole edit, and a store makes
  the loss permanent. Corrected on the unit before the claim shipped.
- Refusals name themselves rather than returning a generic no: no room to
  the right (and what to do instead), a span fed from another row, or a
  target column that is already free and needs no splice at all.
- Amp detection on the grid is alias-hardened. Grid ids alias mod 128, so FX
  Return (186) reads as 58 and would pass for an amp in a naive scan, putting
  "before the amp" in front of the wrong block. It now resolves against the
  status dump (issue #10 asked for this).


### Added (splice, 2026-08-24)
- `FM9.splice_block()`: insert a block into a packed row by displacing its
  neighbours right and re-cabling the span, for the case add_block cannot
  serve - a pre-amp lane with no free pass-through cell (issue #10). Success
  means a live signal path proven by walking Input to Output, not that the
  expected blocks are present.
- `fm9/signal_path.py`: the grid walk, lifted out of tools/path_audit.py so
  the library can use it. tools/ is not a shipped package, so the device
  layer could not have imported it there without breaking an installed copy.
  path_audit re-exports the names it always had.
  Refuses, rather than guessing, when the row has no slack to the right,
  when the target column is already free, or when the span is fed from
  another row.
- docs/PROTOCOL.md findings 25 and 26: displacement preserves a block's
  whole parameter array, channel and bypass state; splicing into a packed
  row works and needs slack to the right.

- `resolve_aliases`, `scene_alive` and `walk` moved from `tools/path_audit.py`
  to `fm9/signal_path.py`, with `path_audit` re-exporting all three so every
  existing import keeps working. `pyproject` ships `fm9` and `server`, not
  `tools`, and 0.3.1's `fm9/health.py` imports the walk from `tools`, so a
  packaged install would not have found it. `health.py` now imports from the
  shipped module.

### Fixed (cable removal, 2026-08-24)
- Cable removal is decoded, and always was: the routing message (sub 0x35)
  carries an op byte, `ROUTING_DISCONNECT = 0x02` has sat beside
  `ROUTING_CONNECT` in the codec since the beginning, and nothing had ever
  sent it. Hardware-verified on fw 12.00 - it clears the mask, is
  repeatable, is idempotent rather than a toggle, and is SELECTIVE on a
  cell with several feeds, which is the property issue #10's splice needs.
  The planned MIDI Monitor sniff session is unnecessary.
- The simulator's undecoded report no longer flags same-row cable draws on
  rows 3 and 4 as unverified; both are hardware-confirmed (row 4 in the
  2026-08-21 session, row 3 while building a preset from scratch). It was
  telling users to go and confirm something the ledger already recorded.
- docs/PROTOCOL.md finding 24, with finding 6's "the removal message is
  UNKNOWN" marked superseded, and cable removal struck from the undecoded
  territory list.

### Fixed (prompt shape, 2026-08-24)
- The reply shape in the planner prompt is derived from `PLAN_SCHEMA`
  instead of hand-written. It had drifted to six action kinds while the
  schema and the validator both accepted eleven, so `add_block`,
  `bind_pedal`, `rename_preset`, `rename_scene` and `store` were absent
  from the shape the model was shown - and on the Grok backend the prompt
  said six while `--json-schema` enforced eleven.
- `_validate` uses the same derived list, removing the third hand-synced
  copy. Tests fail if the prompt, the validator and the schema separate
  again.
- Measured rather than assumed: this changed no output on
  claude-sonnet or grok-4.6 for a request needing two of the five missing
  kinds. Both already emitted them, because the SYSTEM text describes all
  five in prose. The contradiction was real but recoverable, so this is a
  correctness and maintenance fix, not a capability gain.

### Fixed (refusal wording, 2026-08-29)
- A one-action plan is no longer told that its remaining actions were
  skipped. There were none. 0.3.1 fixed the crash that made this line
  unreadable; the line itself is still false, and now counts what it skipped.
- The refusal names the wall it actually hit. It read "no free pass-through
  cell any of the amp", the raw position enum in a sentence, and one sentence
  covered three different situations. An empty slot has no grid cells at all,
  not even pass-through cells (finding 18), so it is pointed at
  `tools/build_from_scratch.py`, the thing that builds into one. A grid that
  did not answer is neither case: it says so and prescribes nothing, because
  sending someone to load a different preset over what may be a cable or
  FM9-Edit holding the port is worse than saying "unknown".

### Fixed (simulator, 2026-08-29)
- The zeroed GET is a read again. `build_get_param` sends sub 0x09 with value
  0.0, byte-identical to a discrete write of zero, and the simulator wrote it:
  a query destroyed the value being queried. `test_zeroed_get_is_noop` exists
  to catch exactly that and passed anyway on a fast machine, because the
  settle window served the read from a pre-write snapshot while the live
  buffer had already been zeroed. On CI, slow enough for the window to lapse
  first, it failed - on `main` at v0.3.1 and on every open PR. The no-op the
  code's own comment described is now implemented, scoped to continuous
  parameters, since that is where the collision is; an enum write of ordinal 0
  is a real write and still lands.

## 0.5.0 (2026-08-30)

A graphic EQ you can read, panels organised by what a block does, and the
answer to "why did that change do nothing". That last one turned out to be
three separate causes wearing the same disguise.

### Added
- **The graphic EQ is drawn as a graphic EQ.** Vertical faders, zero as a line
  across the middle, in its own full width panel rather than a 340px column of
  the tone grid. Ten rows of numbers is a spreadsheet of an EQ, not an EQ: the
  point of the control is that the curve is a shape you read at a glance.
- **Seven starting curves and one click back to flat.** Scooped, mid push,
  tighten the low end, warm, bright, clean up a boxy tone, and flat. A curve is
  one batched write, so it takes one undo snapshot and cannot end up half
  applied. These are curves this project drew and the panel says so; nothing
  here comes off the FM9.
- **The bands are numbered and the strip names the region** (LOW through HIGH)
  rather than carrying frequencies. The catalogue gives each band a frequency
  label, but they are not ascending and one value appears twice, because
  GEQ_TYPE is an eighteen value enum selecting the band layout and one label
  per parameter cannot describe eighteen layouts. A wrong frequency on a fader
  is worse than a number that is simply true.
- **Four panels instead of one column flow**: AMP & CAB, GRAPHIC EQ, EFFECTS,
  DYNAMICS & LEVELS. Two sections would not cover the rig: a noise gate, a
  compressor and a volume block are not effects in the sense a player means,
  and filing them under EFFECTS to make a two way split come out even would be
  a tidy looking lie about what those blocks are. Each folds, so a preset with
  six effects no longer pushes the amp off the screen.
- **The page says what is driving each parameter.** All 32 modifier slots are
  read on every poll (about 0.14s), and a driven parameter shows its source and
  is not draggable. This is also the only honest answer to "is that a pedal wah
  or an auto wah": the FM9 has no auto wah type, a wah is whatever its sweep is
  attached to.
- **Assign and remove Pedal 2 from any continuous parameter.** Hover a row for
  the P2 button; the badge on a bound row removes it. Several parameters can
  share Pedal 2, one modifier slot each, and the reply says how many of the 32
  are left. Pedal 1 is the player's global volume and is never referenced.
- **The wah sweep, frequency limits and resonance are on the page.** The wah
  whitelist was Level and Drive, so the one parameter that answers the pedal
  question was never drawn.

### Fixed
- **Modifier writes followed the wrong sequence.** Finding 17 is targets last:
  the slot's own fields as continuous writes first, then target effect, target
  param and source as discrete writes. The code did the opposite, which is the
  shape finding 16 describes: reads healthy, survives a store, and comes back
  with target and source zeroed once the preset reloads.
- **Modifier bindings are cloned, not invented.** Finding 12 says a binding
  written from scratch comes out reversed or dead, and the working practice is
  to clone a proven slot. A slot this tool builds from defaults is now excluded
  from the donor pool, or a default would launder itself into something the log
  calls a clone, one slot at a time.
- **Binding no longer claims the sweep works.** Live modulation is invisible to
  every read the protocol offers and a dead binding reads byte identical to a
  live one, so a field read back proves the slot was written and nothing about
  whether the pedal moves anything.
- **A bypassed block looked exactly like an engaged one in the parameter
  panels.** The signal chain drew it dashed; the panels had no idea, so a
  switched off block got a full set of live looking sliders. You drag one, the
  write lands, it verifies, and you hear nothing. Reported as "changing the
  drive pedal has no effect", on a preset whose Drive block was simply off.
  Bypassed groups now carry a badge that is also the fix: one click engages the
  block.
- **The planner is warned about both silent write cases**, a bypassed block and
  a modifier driven parameter. "Verified" on a change with no audible effect is
  the most misleading thing this tool can say.
- **The graphic EQ faders were dead on arrival.** Moving the EQ into its own
  panel left the listeners bound to the old container by id. Markup right,
  write path right, API call right, control does nothing, and 501 tests passed
  over it because none of them dragged anything. Every control container is now
  wired through one list.
- **A row without a data-key could freeze the parameter panel for the rest of
  the session.** Both drag handlers read the row before clearing the flag that
  suppresses repainting, so a throw between the two left it set. The modifier
  driven row is exactly such a row shape.
- **A modifier read could drop the link.** Any exception from the state poll
  becomes a disconnect and a red light; 32 unguarded reads were added to that
  path. Guarded per slot and at the call site.
- **Going offline left the EQ panel live**, faders drawn and FLATTEN ALL armed
  over a page reading "awaiting link", and left the amp and cab pickers naming
  a preset no longer loaded.
- **The catalogue's band label reached the log**, so a fader that deliberately
  shows no frequency was recorded as "250: 2" in the one place that records
  what was written to the rig.
- **unbind_pedal rendered as "Mix: null"** in plan cards, having no describe()
  branch of its own.
- **The pedal button and the server disagreed about what is bindable.**
  FUZZ_TYPE is a selector whose unit is `unverified` rather than `enum`.
- **path_audit assumed unidentified blocks pass signal and said nothing.** A
  scene called alive on the strength of an assumption is a weaker claim than
  one called alive without it, and the difference was invisible. Found while
  diagnosing a silent preset that turned out to contain two engaged blocks with
  no registry entry.

## 0.4.1 (2026-08-30)

Three connection bugs, all found by plugging a cable in and out. Between them
the app could not tell you the truth about whether your rig was there.

### Fixed
- **A device plugged in after the server started was invisible.** `FM9.__init__`
  calls `mido.get_input_names()` fresh on every attempt, so discovery looked
  like it could not go stale. The rtmidi backend enumerates through a CoreMIDI
  client it holds for the life of the process, so a server started while the
  FM9 was off never saw it appear however long the poll retried. The tell was
  exact: a fresh python process listed the FM9 and opened it happily while the
  running server, same machine, same moment, reported not connected.
- **Reconnection is automatic.** `get_fm9()` re-enumerates the bus before
  rebuilding the handle, throttled to once every two seconds. Plugging the
  cable in reconnects within one poll with nothing to press. A reload was
  measured at about eleven milliseconds with no file descriptor leak before
  being put in a loop.
- **An unplugged device still reported connected.** An open MIDI port is not a
  connected device: pulling the USB leaves the handle valid, writes go nowhere
  and reads simply time out. `snapshot()` took that at face value and returned
  connected with no preset, no scene and no blocks, so the link light stayed
  green over an empty page. It now gives up the moment `current_preset()` comes
  back empty, and gives up BEFORE the eight scene names and the status dump,
  each of which would otherwise wait out its own timeout and freeze the poll
  for ten seconds on a device that is not there.

### Added
- The LINK pill is a button. Automatic reconnection is the mechanism; this is
  for the person who has just plugged something in and wants to press
  something. A failed look says why, including to check FM9-Edit is not
  holding the port.

### Verified
On hardware, both directions: the cable out turns the link red and hides the
panels that need the rig, and the cable back in turns it green again on its
own. Also closed the loop 0.4.0 left open, designing a change, checking it for
drift against the live unit, transmitting it, reading Mid back at 6.25 from
5.0, and undoing it back to 5.0.

## 0.4.0 (2026-08-30)

**It works with the amp switched off.** Design tones on a plane, browse and
use other people's, and let it fix what it finds wrong. Five new capabilities
rather than fixes, which is why this is a minor bump and not a patch.

### Added
- **Design with the rig unplugged.** Exactly one line in the planning path
  needed hardware, the snapshot read for context, so it now falls back to the
  last real reading of the session. Everything you build is kept in a DESIGNED
  PRESETS page and goes out when the FM9 comes back. Reconnecting is a merge,
  not a hope: a design records the value each action was computed against, and
  SEND re-reads and compares first, reporting clean, or naming exactly what
  moved underneath the edits and asking. A queue that applied blindly would
  overwrite a change made on the front panel in between and nobody would know.
- **Plan with no reading at all.** A build is not an edit: "a Steve Lukather
  lead in scene 4 of a new preset" needs nothing from the rig. The planner is
  told what IS structurally true of every FM9 rather than only what is missing,
  and asked to state its assumptions rather than refuse. Relative requests are
  still turned down, because there is nothing to be relative to.
- **Design for a rig you do not own.** A rig profile describes a preset's
  shape: which blocks it has, how they are cabled, the scene names, which amp
  and cab are emulated. Never the parameter values, because a full dump of
  those IS the preset and many presets came from paid packs. Enough to design
  against, not enough to reconstruct a tone.
- **A recipe browser.** Other people's tones, read straight from the public
  recipes folder with no account and no sign-in. USE validates every step
  against YOUR device before proposing anything, which is what makes a recipe
  portable rather than a preset file with extra steps.
- **A sharing service that cannot lose anything.** service/worker.js: an inbox
  and a counter, the only two things GitHub cannot do. Content stays in the
  repository, so if the service is down browsing and using still work. A recipe
  is written to disk and queued BEFORE any network call, and an entry clears
  only on an explicit 2xx. Counting transmits rather than downloads, ranked on
  the last thirty days so a good new tone can surface.
- **FIX IT on preset health.** One button for the whole report. Levels are
  arithmetic so the exact change is stated; making a cloned scene its own sound
  is taste so it goes to the planner. It never applies anything: it fills the
  plan box behind the same confirm gate as everything else, and the scan
  re-runs afterwards so "fixed" is a measurement.

### Changed
- **Sharing no longer opens a GitHub issue.** An issue is not a container for a
  recipe, the tracker would silt up, and it asked a guitarist to learn a
  developer's tool before contributing. Recipes save locally and copy to the
  clipboard, and for anyone who does use GitHub there is a prefilled new FILE
  in recipes/ where it belongs.
- **Panels that need the rig are hidden when it is away**, rather than dimmed.
  Out of the layout and out of the tab order in one move, which removed the
  bookkeeping that tracked which controls were already disabled. The banner
  names what went and what still works.
- **Type sized for reading.** The scale ran 8.7px to 15.75px on a 15px root.
  It now runs 12.5px to 20.8px on a 16px root, with the small end grown by more
  than the large end, and an A/A control in the header that multiplies the lot
  and is remembered per browser.

### Fixed
- A recipe exported from a design could carry a name the sharing service
  rejects and that cannot be a filename: to_recipe replaced spaces and nothing
  else, so "Steve Lukather: Dumble ODS lead" became
  steve-lukather:-dumble-ods-lead. One slug rule now, in one place.
- The test suite could write to the real save whitelist. conftest never
  isolated store_slots.json, so a test that forgot to monkeypatch it wrote to
  the live file. Pinned session wide beside the .env isolation that exists for
  exactly the same lesson.
- Widening the simulator for cab auditioning removed the guard that made a
  zeroed GET a no-op, so reading a parameter started zeroing it. Sub 09 00
  carrying zero is the read, whatever the parameter kind.

### Verified
Hardware: scenes, the routing grid, auditioning, undo and A/B, the health scan
and its clone check, blast radius, and saving. Simulator and a stub service:
offline design, the conflict check, recipes, and the zero-loss outbox including
an item queued while the service was down and flushed when it returned. The
final transmit of an offline-designed tone has not yet run on hardware.

## 0.3.1 (2026-08-29)

A patch on the day 0.3.0 shipped, because the first person to run it outside
this machine hit a crash on his first real prompt.

### Fixed
- **Transmit crashed instead of explaining itself.** On an empty preset,
  `add_block` correctly refuses (nothing to place onto), and the server then
  reports that it skipped the remaining actions. That report carries
  `"action": null`, because it is about the plan rather than about one action.
  The browser read `.kind` off it, threw inside the result loop, and replaced
  the server's explanation with "Cannot read properties of null". The guard
  itself matters: running the rest would bind modifiers to a block that never
  landed, observed on hardware on 2026-08-20. It now reads "plan halted:
  remaining actions skipped: add_block failed". Reported by Brian; reproduced
  through the real transmit path in a browser rather than a stub.
- **Result cards took the wrong outcome after any extra result.** Results do
  not map one to one onto cards: a failed undo snapshot is prepended and the
  skip note appended. The card cursor now advances only for real actions.
- **The settings modal put its second panel off the screen edge**, being a flex
  row with more than one child.
- **The API key box grew to 340px tall.** `#aikey` carries `flex: 3 1 340px`
  for the horizontal layout, an id beats a class, and in the stacked modal that
  basis became a height.

### Added
- **A save button.** Until now the only way to keep a change was to type "save
  this to preset 139" and hope the planner agreed, which is a poor interface
  for the one action that cannot be undone. It aims at the preset you are
  looking at, offers only slots you marked disposable, shows both the wire and
  the FM9-Edit number, says what each slot currently holds, and states plainly
  that undo does not cover it.
- **The save whitelist is visible and editable in the app.** It lived only in
  `.env`, so the boundary protecting 512 presets was invisible from the product
  that enforces it: it was authorised in conversation, written to a gitignored
  file, and days later its owner could not check it. Now in settings, with
  clickable examples, and a preview that names what a change would newly expose
  BEFORE it is applied rather than after. An explicit environment variable
  still outranks the app, so a deliberate pin cannot be moved from a browser.

### Changed
- One type scale of six steps replaces seventeen font sizes, several of them a
  hundredth of a rem apart. Section names were doing the most work at the
  smallest size on the page and now lead; the amp and cab pickers read as the
  headline of the tone panel rather than a caption under one; the logo is in
  the header at a size you can actually see.
- Cab descriptions are no longer clipped. Two lines still cut the long ones:
  the longest in the catalogue runs to 268 characters, the median is 56.
- The empty log now says what this does that FM9-Edit cannot, and retires
  itself the moment anything is logged.

### Internal
- **The test suite could write to the real save whitelist.** `conftest` never
  isolated `store_slots.json`, so a test that forgot to monkeypatch it wrote to
  the live file. Relying on each test to remember is the wrong shape for a
  safety boundary; it is pinned session wide beside the `.env` isolation that
  exists for exactly the same lesson, and the suite is verified to leave the
  real file byte identical.

## 0.3.0 (2026-08-29)

**The UI stops being a poster.** It had four interactive controls: a prompt
box and three buttons. Everything else was a readout, so the moment you wanted
to change a scene, mute a delay or nudge a mid you were back in FM9-Edit, and
a tool you leave in the middle of a session is one you stop opening. Every
panel is now a control surface.

The rule the release is built to: if you have to switch to FM9-Edit mid
session, we have already lost.

### Added
- **Scene and preset switching.** Eight footswitch-shaped scene buttons posting
  straight to the device with no planner in the way, and a searchable preset
  popover on the header pill. `set_scene` was already the one action gig mode
  permits, so the architecture always treated it as the safe operation.
- **The signal chain is the real routing grid.** Rows, columns and cables as
  the unit has them, drawn in SVG, with the live path lit and anything the
  signal never reaches left grey. Blocks are clickable: bypass on the block,
  channel on its letter. The traversal is the path audit's own, extracted into
  `walk()` rather than reimplemented, because five silent-scene classes were
  found the hard way getting it right.
- **A tone panel you can turn.** Grouped by block, in the unit's own labels,
  ranges and units from the registry rather than a table in the browser, with
  every published-range value a slider you drag. The amp model and cab
  description are shown at last; both were being read on every poll and thrown
  away.
- **Auditioning amps and cabs.** 331 amps and 2,237 cabs, filtered as you type
  and stepped with the arrow keys while you keep playing. Searchable by name
  and by what the cab actually is. New `set_cab` action kind, since bank and
  slot are two parameters and the slot ordinal lives in the raw wire rather
  than on its declared display scale.
- **Undo and A/B compare**, which the FM9 has neither of. A snapshot is a
  silent read of the whole edit buffer, about a quarter second, taken
  automatically before every write, so undo is always armed. A restore is a
  diff, not a replay. Recalling A captures B first, so A/B is a round trip.
  In memory only, and refused across a preset change or in gig mode.
- **A save button.** Until now the only way to keep a change was to type
  "save this to preset 139" and hope the planner agreed, which is a poor
  interface for the single action that cannot be undone. SAVE TO PRESET
  offers the owner's whitelisted slots and nothing else, never a free-text
  number, shows both the wire and the FM9-Edit number for each, says what
  each slot currently holds, and asks before it overwrites. It states plainly
  that undo does not cover it, because undo restores the edit buffer and
  cannot un-write a preset slot. It aims at the preset you are looking at:
  save means save THIS preset to anyone who has used an editor, so the
  selector defaults to the loaded slot. When the loaded preset is not one you
  marked disposable, the panel says so rather than quietly offering a
  different slot, which is the exact failure the whitelist exists to prevent.
- **Preset health scan.** The audits that have existed as command-line scripts
  for weeks, on a screen: every named scene alive or dead with the hop that
  broke the path, amp level and volume gain side by side, and the findings
  underneath. Audible, so it is a POST, never on the poll, refused in gig mode,
  and it restores the scene it started from.
- **A clone check**, new. Two scenes with the same bypass and channel set are
  the same scene, necessarily, because parameters live on the channel. It
  needs no extra reads. Run against preset 151 it found THREE identical
  scenes where the ear pass had found two, one of them named PITCH with no
  pitch block engaged. Three separate audits had passed all of them.
- **Blast radius.** Changing a parameter moves every scene sharing that
  block's channel, and the tool now says so by name, on the plan card and in
  the log. Those scenes now light amber with a WILL CHANGE badge at
  the same visual weight as the active scene, rather than the fact living in
  small print under the plan card.
- **`tools/ui_probe.py`.** Headless Chrome over the DevTools protocol:
  screenshots the page and evaluates JavaScript inside it, so states that need
  triggering can be set up with the app's own functions and read back with
  `getComputedStyle`. `kb/UI_VERIFICATION.md` makes rendering before signing
  off a standing rule.

### Fixed
- **Restores wrote display values, which silently loaded the wrong cabinet.**
  A cab slot is an ordinal held raw in the wire, so display 1.64 on a 0-1023
  scale came back as cab 1 instead of cab 105 while the undo reported success.
  New `FM9.set_param_wire` writes exact wire values verified by integer
  equality, and tries both encodings because `spec.kind` does not distinguish
  them: `CABINET_TYPE1` declares float while holding an ordinal.
- **`restore()` re-read block channels between writes.** The FM9 applies writes
  asynchronously and serves pre-write state to reads inside that window, so a
  status dump taken straight after `set_channel` reported where a block used to
  be. It never fired on hardware because the writes happened to be slow enough.
  Positions are tracked instead. Recorded in KNOWN_QUIRKS.
- **The audition popover was destroyed by its own panel.** It was parented into
  the panel that the five-second poll repaints, so each picker opened exactly
  once and then threw. It is anchored by measurement now.
- The blast-radius warning stayed lit after a plan was discarded, until the
  next poll happened to repaint it.
- AI settings held a full console on the main page for a once-a-month setting.
  Now behind a header gear, which no longer carries the backend name, because a
  label on a control names the control and it made the gear look like it was
  called AUTO.
- The signal chain overflowed its panel on any preset past twelve columns. It
  scales to fit now, measured at four viewport widths.
- Removing the old block-list CSS took the tone panel's stylesheet with it, and
  342 tests passed over a page rendering in browser defaults. Tests now require
  a rule for every class the page uses.

### Simulator
- Discrete writes apply to any parameter, not only ones the reference calls
  enum. Hardware accepts one on `CABINET_TYPE1` and stores it exactly, so cab
  auditioning worked on the unit while being untestable in the double.

## 0.2.0 (2026-08-28)

**Bring your own AI.** The natural-language planner now runs on the Claude
Code CLI, the Claude API, the Grok CLI, or any OpenAI-compatible endpoint,
chosen from a panel in the UI rather than by editing a dotfile. That last
option covers local models through Ollama or LM Studio, anything behind
OpenRouter, and via CLIProxyAPI it reaches Codex, Gemini and Kimi over
their own OAuth logins. A fresh checkout still needs no key and no
configuration: the Claude CLI remains the default when nothing is set.

Underneath it, the groundwork for supporting more than one device: the
never-brick guard is now architecture rather than one class's policy, and
the adapter contract states what a device can actually answer instead of
assuming every method works everywhere.


### Changed (2026-08-24 session)
- The adapter contract declares capabilities instead of assuming them.
  fm9/adapter.py adds Capabilities and a ranked ReadPath (NONE <
  OBSERVED < DEVICE < EARS, making invariant 4's ranking comparable so a
  mixed rig reports its weakest link rather than an average). The
  contract previously assumed every method was answerable everywhere,
  which left an adapter on a device without a read path choosing between
  inventing state and failing; now it can say what it cannot do and the
  layer above degrades openly. Declaring is deny-by-default, so an
  unfinished adapter under-promises. A second real device is what
  surfaced this, including the shape the contract could not express: one
  device whose read and write paths are different transports.
- Invariant 0 is now architecture rather than one class's policy.
  fm9/safety.py holds the deny-by-default SendGuard every device
  transport passes through; a transport that declares no allowlist can
  send nothing. The never-brick check previously lived inside
  FM9._send, which protected the FM9 and left any second adapter with
  no protection at all. The FM9's own allowlist and behaviour are
  unchanged, and the refusal is still a PermissionError for callers
  that predate the lift.

### Fixed (2026-08-25 session)
- ToneX frame decoding was correct by luck rather than by
  understanding. It ignored HDLC byte stuffing entirely (0x7d escapes,
  next byte XOR 0x20; present in 36 of the 128 reference captures) and
  left the frame check sequence unverified. tools/tonex_decode.py now
  unstuffs and validates the FCS, which is CRC-16/X-25: established
  empirically rather than assumed, since of the five common CRC-CCITT
  variants it is the only one that validates, and it validates all 128
  captures. A validated CRC is the difference between a frame parsed
  correctly and one parsed without crashing. Decoded values are
  unchanged (the escapes fell in the FCS region), so earlier analysis
  stands. Frames without delimiters report the CRC as unchecked rather
  than as valid.

### Added (2026-08-24 session)
- tools/tonex_probe.py: read-only Phase 1 feasibility probe for the IK
  Multimedia ToneX pedal. Outbound traffic is limited to Program and
  Control Change by the shared SendGuard, and the pedal's serial
  control port is opened read-only, since firmware and bootloader
  traffic travels over that kind of channel on an undecoded device.
### Fixed (AI settings review round two, 2026-08-24)
- Selecting Auto clears a `PLANNER_BACKEND` pin instead of being unable to
  override one. A stored backend of `""` used to be indistinguishable from
  never having chosen, so the panel could not honour its own Auto setting:
  GET reported the pin again, the dropdown snapped back after a successful
  save, and `candidates()` stayed pinned. The choice is now recorded as a
  choice, and applying it writes an explicit blank, which `planner._env`
  reads as deliberately unset. A file with no backend key at all still
  defers to the environment, because that is not a vote for anything.
- A save no longer pins base URL or model values that came from the
  environment. Both boxes were prefilled from the merged view and posted
  back, so opening the panel and clicking SAVE wrote a `.env` value into the
  file, and since the file outranks `.env`, editing it there afterwards
  silently did nothing. The boxes now carry only what is stored, with the
  environment's value shown as a placeholder, which is the shape the key box
  already had. Found by an independent review; the key half was fixed one
  round earlier and not generalised.
- `ai_settings.json` is written `0600`. It holds an API key and was created
  with the process umask, commonly `0644`, so on a shared machine any other
  local account could read it. A file predating the fix is tightened on the
  next save. Patch supplied by @Triumph1701 on #25.
- Log lines are escaped. It was the last place model output reached
  `innerHTML` raw, including `plan.clarification` and planner error text.
- A save cannot land in the middle of a plan. Planner configuration lives in
  `os.environ` and is reread inside each backend runner, so a save arriving
  after `candidates()` chose a backend could send the new key at the old
  URL. The planner call holds a settings lock, and a save that cannot take it
  is refused with a sentence rather than left to hang for the length of a
  plan.

### Added (AI settings in the UI, 2026-08-24)
- `GET`/`POST /api/ai-settings`, following the existing `/api/gig` pair, and
  an AI SETTINGS panel in the UI: pick Claude Code CLI, Claude API, Grok CLI
  or an OpenAI-compatible endpoint, with CLIProxyAPI's default prefilled.
  Takes effect on the next prompt with no restart and no `.env` edit
  (issue #24).
- The choice persists in a gitignored `ai_settings.json`, with the
  environment as the fallback when the file is absent. Precedence, highest
  first: the file, the environment including `.env`, the built-in default.
  Outranking is not erasing: applying a choice now releases the variables it
  is not setting, restoring whatever the user had, and only ever removes a
  value this module wrote. Clearing them meant that anyone with
  `ANTHROPIC_API_KEY` exported lost the Claude API backend the moment the
  server started, having changed nothing and been told nothing, and that the
  key was stripped from the environment handed to the `claude` subprocess
  even though the allowlist passes it deliberately.
- Only what the user typed into the panel is written to the file. A save
  used to be seeded from the merged view, so an exported key or a model id
  from `.env` was copied into `ai_settings.json` on a save that had nothing
  to do with either. Since the file outranks both, that also turned a later
  edit of `.env` into a silent no-op, which is a genuinely horrible thing to
  debug.
- The API key never reaches the browser. `GET` returns a `hasKey` boolean
  and nothing more; a blank or absent key on `POST` keeps whatever is
  stored, and removing one takes an explicit `clearKey`.
- Backends the host cannot run are shown disabled with the reason, because
  a dead option that silently falls through to something else is worse than
  no option. Disabled now means only "you cannot fix this from this panel":
  a missing `claude` or `grok` binary is a fact about the host, while a
  missing key or base URL is a box on the same form, so those backends stay
  selectable and say what they still need. Disabling them was a closed loop
  (@Triumph1701 on #25): the Claude API option needed a key to be
  selectable, and needed to be selected for the key box to appear, which
  made the one backend a new user reaches for first unreachable. Saving a
  pinned backend that still cannot run is refused in a sentence instead,
  since pinning disables fallthrough by design.
- Only the controls a backend actually reads are shown, for the same reason.
  The four backends read different variables and two read none at all: the
  Claude CLI has nothing to configure and its model is a planner constant;
  the Claude API takes a key (`ANTHROPIC_API_KEY`) and its model is also a
  constant; the Grok CLI takes a model (`GROK_CLI_MODEL`) and no key; the
  OpenAI-compatible path takes all three. Auto carries the same three as
  the OpenAI path, since a configured endpoint is the planner's first
  candidate.
- Model strings are treated as untrusted input, because this release invites
  people to point the tool at endpoints they do not control. The answering
  model is written with `textContent`, `/models` ids are set as option
  properties rather than interpolated into a `value=""` attribute, and every
  string on a plan card (all of it model output) is escaped.
- Listing Anthropic models is bounded at 10s with one retry, like the grok
  and endpoint listers. Without a timeout a hung network pinned a threadpool
  worker for the SDK default plus its retries, and the panel looked frozen
  rather than slow.
- Keys and models are stored per backend, so a router key cannot quietly
  become an Anthropic one, and a value cannot steer a backend that never
  reads it.
- Boxes that can be left blank say so. Model boxes read "model (optional)",
  since every backend has a default. The key box states the whole rule,
  "API key (required for Claude API but optional for others)", rather than
  a per-backend word: the Claude API cannot run without one, an OAuth
  router wants none, and nobody should go hunting for a credential nothing
  asked for.
- Every backend now has a model box, since the two Claude models became
  configurable, and each box offers suggestions from whatever can actually
  answer: `grok models` for the Grok CLI, `GET /models` for an
  OpenAI-compatible endpoint, the Anthropic models API when a key is
  configured, and the aliases the claude CLI documents. The panel says
  where each list came from, and every box stays typeable, because a list
  that cannot be overridden is worse than no list once it goes stale.
- `GET /api/ai-settings/models?backend=` exposes that listing.
- A finished plan says which backend and model produced it, so a
  wrong-sounding plan is attributable to the model rather than the tool.
- `fm9/ai_settings.py` deliberately changes no planner behaviour: it writes
  the saved choice onto the same environment the planner already reads, so
  a UI selection and a hand-edited `.env` take exactly the same path.


### Added (planner backends, 2026-08-24)
- **OpenAI-compatible planner backend** (`PLANNER_BASE_URL`): reaches
  CLIProxyAPI, and through it Claude Code, Codex, Grok, Gemini or Kimi over
  their own OAuth logins, plus local models and OpenRouter. No new
  dependency - urllib, not the openai package. `PLANNER_API_KEY` is
  optional by design, since an OAuth router needs none.
- **Grok CLI planner backend** (`PLANNER_BACKEND=grok`), with replies
  constrained by `--json-schema` to `PLAN_SCHEMA`. Verified on grok 1.0.5.
  Reached only when pinned or through a router, never auto-selected.
- **Failure taxonomy and per-attempt record** in `plan()`, implementing
  @Triumph1701's contract from #7: transport or malformed output is a
  backend failure and moves on; a reply that parses but says nothing is a
  planner result and does not fall through; the aggregate error is raised
  only after every candidate is exhausted, naming each attempt.
- Every plan now carries `backend`, `model`, `plan_quality` and `attempts`,
  plus one log line, so backend choice is visible before the settings UI
  lands.
- `PLANNER_BACKEND` pins a backend and disables fallthrough; a deliberate
  choice must not quietly resolve to another vendor's model.
- README: planner backend table, and instructions for installing and
  running CLIProxyAPI yourself. It is a separate service, deliberately not
  vendored and not a dependency.

### Fixed (planner backends, 2026-08-24)
- `_env` distinguishes a variable that is ABSENT from one that is PRESENT and
  empty. Only an absent one falls through to `.env`; a blank means
  deliberately blank and stops the search, resolving to the built-in default.
  Treating them the same left no way for a layer above to say "not set", so
  the settings panel selecting Auto could not clear a `PLANNER_BACKEND` pin
  written into `.env` (@Triumph1701 on #25). A blank still resolves to the
  default, so an empty `CLAUDE_CLI_MODEL` means the built-in model rather
  than `--model ""`.
- The Claude API backend is bounded by `PLANNER_TIMEOUT` like every other
  backend, with timeouts and connection errors mapped to `timeout` and
  `transport` failures. It was the one backend not honouring the contract
  this work introduced: the SDK default plus its retries applied, so a stuck
  call hung `/api/plan` with no failure and no fall-through.
- `GROK_ENV_KEYS` includes `NETWORK_ENV_KEYS`. Withholding the proxy and CA
  variables from the grok CLI reproduced exactly the failure that set exists
  to prevent, and the test asserted the broken behaviour. Narrowing per tool
  means narrowing which credentials it sees, not starving it of the shell:
  no Anthropic or cloud keys reach it, which the test now checks explicitly.
- The test isolation fixture clears `CLAUDE_CLI_MODEL` and
  `CLAUDE_API_MODEL`. Both are new here and were left out, so a developer
  with either exported got a false failure from the test asserting the
  built-in default.
- Planner subprocesses get an environment allowlist instead of
  `os.environ`. The `claude` binary had been receiving every secret in the
  process; with a second vendor's CLI in play an xAI binary would have
  received `ANTHROPIC_API_KEY`.
- The Claude CLI path gained the timeout and empty-output cases it was
  missing, and reports the model from `modelUsage` rather than a top-level
  `model` key, which a real envelope does not carry - reading `model` alone
  reported the alias we asked for.
- Planner subprocesses get an environment allowlist wide enough to keep
  working setups working: proxy and CA variables, the CLI's config dir, and
  the Bedrock and Vertex routes are configuration rather than foreign
  secrets. Each CLI still sees only its own credentials.
- `PLANNER_TIMEOUT` is parsed safely and per call. It was an unguarded
  `int()` at import, so a dotenv-style `PLANNER_TIMEOUT=300  # comment`
  crashed `import fm9.planner` and took the server down at startup, for
  users who never plan anything.
- The OpenAI-compatible path enforces a real wall-clock deadline. urllib's
  timeout bounds each socket operation, not the attempt, so a router that
  trickles its body never tripped it and `/api/plan` hung with no timeout
  failure and no fall-through.
- The two Claude models are configurable instead of hard-coded:
  `CLAUDE_CLI_MODEL` and `CLAUDE_API_MODEL`, defaulting to the previous
  constants (`sonnet` and `claude-opus-5`). The CLI has always taken
  `--model` and the SDK a model id, so neither needed to be fixed, and
  wanting Opus on the CLI path is a reasonable thing to want. Read per call,
  so a change does not wait for a restart, and passed through the subprocess
  allowlist.
- JSON extraction tries each `{` with the stdlib decoder and prefers the
  last plan-shaped object. Slicing from the first brace to the last one
  broke on real local-model output: a reasoning model drafts an object and
  then emits its final answer, and that span covers both, failing with
  "Extra data: line 2 column 1". Found by pointing the OpenAI-compatible
  backend at LM Studio, which is what issue #7 asked for. Counting braces
  in one pass is not enough either, as @Triumph1701 pointed out on #21: a
  model that abandons a draft part way leaves an unclosed brace and an
  unterminated quote behind, which pin the depth and swallow the rest of
  the reply, losing the real answer that follows. Trying each start in turn
  costs a bad start only that start.
- `.env` values are unquoted. `PLANNER_API_KEY="sk-local"` was sending
  `Bearer "sk-local"`, and a quoted base URL failed as an unknown url type.
- Plan validation runs inside the per-backend try, so a reply that parses
  as JSON but is shaped wrongly (`{"actions": 42}`) falls through to the
  next backend instead of aborting the run untyped.
- An explicit JSON `null` for a non-nullable action field no longer costs
  the whole plan a 502; nulls are replaced, not merely defaulted when absent.
- `_api_available()` checks for the key instead of the mere existence of a
  `.env` file, so a router-only install stops offering a doomed `api`
  candidate whose auth noise buried the actionable transport failure.

### Fixed (docs, 2026-08-24)
- docs/HARDWARE-VALIDATION.md is marked as a preserved 2026-08-16 snapshot
  rather than current documentation, listing what has been superseded since
  - the firmware 11.x pin, and its statement that the store command would
  never be implemented in the write path (it is, whitelisted). The body is
  left as written; a dated report is worth more as a record than as a
  document quietly edited to stay true.
- The README's claim that FM9-Edit resets the edit buffer when it connects
  was wrong. Tested with FM9-Edit 1.03.21 on fw 12.00: unsaved edits
  survived the editor connecting, and reads stayed correct while it polled
  the shared port at ~60 msg/s. Buffer edits are lost to a preset load from
  either side, which is ordinary behaviour. Concurrent writes, older editor
  versions and fw 11.00 remain untested and are marked as such.
  docs/PROTOCOL.md finding 23.
- README compatibility table and Protocol Contributions brought current
  with what fw 12.00 has actually proven.

### Fixed (preset numbering, 2026-08-24)
- Tools now print preset numbers both ways: the wire number (0-511) and the
  number FM9-Edit and the front panel show for the same slot (1-512). They
  differ by one, and a bare wire number is how the wrong preset gets
  cleared. Found by the owner cross-checking a built chain against
  FM9-Edit.
- Out-of-range preset numbers are refused instead of believed. The unit
  answers a query for preset 512 with a blank name, and a blank is not the
  `<EMPTY>` marker, so an unguarded read called such a slot OCCUPIED - the
  wrong direction for code choosing where to write.
- `TONECOMMAND_STORE_SLOTS` is documented as wire-numbered: `133-148` is
  what the editor shows as 134-149.
- The two surfaces where being wrong actually costs something now print both
  numbers too, which the first pass missed (@Triumph1701 on #22). The store
  confirmation is the only destructive prompt in the product, and it named a
  slot the owner's own editor disagreed with, so reading the dialog and
  checking FM9-Edit was how a correct operation got aborted or a wrong one
  approved. The live preset readout had the same fault with less at stake.
  Both labels are rendered server side from `protocol.slot_label`, so the
  numbering rule stays in one place instead of being recomputed in the
  browser.
- A store refusal describes the whitelist it is enforcing rather than its
  endpoints. With `TONECOMMAND_STORE_SLOTS=133,150-155`, refusing slot 140
  used to print "configured store slots are 133-155", naming the refused
  slot as allowed and sending the owner off to fix the wrong thing. Runs are
  collapsed, so a contiguous whitelist still reads as one range.
- docs/PROTOCOL.md findings 21-22.

### Fixed (from-scratch tool, 2026-08-24)
- A device NACK during slot selection prints a refusal instead of a
  traceback. `NoEmptySlot` and `FM9NotFound` are both `RuntimeError`, but
  `_request` raises the bare parent, and naming only the children let it
  escape the handler.
- An inverted `--range 449 386` is refused rather than scanning nothing and
  announcing that every slot holds a preset, which told the owner their unit
  was full when it may have been empty. Checked in `scan_slots`, so every
  caller is covered rather than just the tool.
- docs/PROTOCOL.md finding 6 lists row 3 among the verified same-row cable
  runs. Finding 20 added it and the simulator already relies on it, so the
  ledger entry the cable code cites was out of step with the code.
- The fw 12.00 compatibility row for block insert reads plain "Verified":
  this work verified it firsthand on the owner's unit, not via a
  contributor report.

### Added (from-scratch builds, 2026-08-24)
- `tools/build_from_scratch.py`: builds INPUT -> amp -> cab -> OUTPUT into
  an empty preset slot, placing every block and drawing every cable, then
  verifying the chain is continuous. Edit buffer only; nothing is stored.
- `FM9.first_empty_slot()`: finds a free slot, or raises `NoEmptySlot`. The
  build always lands on a slot the device itself reports as `<EMPTY>` and
  refuses when there is none - there is no `--force`, because overwriting a
  preset someone owns should not be one flag away.
- docs/PROTOCOL.md findings 18-20: an empty slot has no grid cells and no
  Input/Output blocks (only the ever-present ids 200/201); placing into a
  blank grid works, arriving uncabled; row-3 same-row cable draws work with
  the general formula, owner-confirmed audible.


### Added (2026-08-23 session)
- tools/apply_template.py: apply any owner-defined 8-scene layout to a
  preset from a mapping file; mechanics only, conventions stay local.
- tools/path_audit.py: end-to-end signal-path proof per scene (grid
  walk, alias-aware, send/return bus, source-block bypass semantics).
- tools/preset_doctor.py: the full verification ladder as one command.
- tools/conventions.py + optional local kb/conventions.json: owner
  conventions (trims, staircase, name vocabularies) enforce only when
  configured; public tools ship without opinions.
- DeviceAdapter contract: slot_name / is_slot_empty (by-number reads).
- Level report: staircase and boost-below-reference checks
  (convention-gated); scene audit: bypassed-INPUT and severed-Return
  flags, dual-instance sweeps.

### Fixed (2026-08-23 session)
- Seven presets carried silent scenes (bypassed Input blocks); the
  class is now flagged by the audit and proven dead-or-alive by the
  path audit.
- Modifier bindings: full revive sequence that survives the device's
  load-time slot validation (docs/PROTOCOL.md findings 16-17); pedal
  delay/multitap bindings restored across the owner's presets.

### Added (empty-slot probe, 2026-08-23)
- `tools/find_empty_slots.py`: reports which preset slots are free, as
  contiguous ranges, and suggests a target for a from-scratch build.
  Non-destructive - it selects nothing, so it is safe to run mid-session
  with a preset you are playing loaded.
- `FM9.slot_name()` / `is_slot_empty()` / `scan_slots()`: read a slot's
  stored name by number, out of flash, without selecting it. fn 0x0D
  supports this and nothing here used it before; every other preset
  inspection in the project discards the edit buffer to do its work.
- `FM9.require_empty_slot()`: gate for building a preset from scratch, so
  a build cannot start by clobbering a preset someone owns. Opt-in target
  check; store stays separately whitelisted.
- `protocol.SlotName`, `decode_name_field()`, `is_empty_slot_name()`, and
  `EMPTY_SLOT_NAME`: the `<EMPTY>` marker is now a first-class concept
  instead of a string no code recognized.
- Simulator models empty slots (`SIM_EMPTY_SLOTS`), including the ghost
  bytes and the all-NUL scene-name fields, so all of the above is
  testable headless.

### Fixed (empty-slot probe, 2026-08-23)
- Preset names are cut at the first NUL instead of right-stripped.
  Clearing a slot overwrites only the first 8 bytes of the 32-byte name
  field, so `current_preset()` had been reporting names like
  `'<EMPTY>\x00 Phat Time'` - the marker glued to the tail of a preset
  that no longer exists. Replaying the new parser over 512 real captured
  name fields changes no occupied name and drops the ghost from all 72
  empty ones. See docs/PROTOCOL.md findings 14 and 15.

## 0.1.0 (2026-08-22)

First tagged release: installation is now repeatable, so the version
number means something.

### Added (release polish, 2026-08-22)
- Packaging: pyproject.toml with declared dependencies and a
  one-command launcher (`pip install -e .` then `tonecommand`).
- README: UI screenshot (captured against the bundled simulator),
  architecture diagram, "What you can say" examples, and an explicit
  capability/firmware compatibility table.
- docs/HARDWARE-VALIDATION.md: the hardware feasibility report,
  relocated from PHASE1-REPORT.md and retitled as public documentation.

### Changed (release polish, 2026-08-22)
- Tagline reworded from "Speak" to "Describe the tone you want":
  the shipped workflow is typed, and the pitch should not promise a
  voice input that does not exist yet.
- test_phase2.py renamed to hardware_regression.py; the two-tier test
  story (simulator suite in CI on every push, 13-check regression on
  hardware) is now documented in the README.
- CI installs from pyproject instead of an ad-hoc pip line, which also
  fixes a dependency typo (httpx2).

### Added (2026-08-22)
- Tone recipes: shareable, cited, replayable builds (docs/RECIPES.md,
  tools/replay_recipe.py, first recipe published). Store is forbidden by
  format; every replay ends in an ear checklist.
- docs/PROTOCOL.md: the hardware findings ledger as a citable spec,
  including the zero-ordinal GET trap, the display-name trap, cable
  encoding status, and the read-honesty ranking.
- Tone lock (tools/tone_lock.py): wire-level regression testing for
  presets; lock a baseline, detect any drifted parameter by name.
- Gig mode: POST /api/gig locks the server to scene changes only (HTTP
  423 for everything else) for the duration of a performance.
- DSP budget advisor (tools/budget_advisor.py): predicts silent insert
  refusals from the owner's own preset library instead of a fake CPU
  model - it correctly "predicts" the stereo-pair refusal of 2026-08-21.

### Fixed
- Ordinal 0 could never be set through the discrete path (zero-valued
  sub 09 is the device's GET); zero ordinals now route through a
  continuous 0.0 write. Earlier zero-ordinal type sets may have silently
  no-opped; hardware re-verification queued.

### Added
- Complete grounding data: amps 331/331, drives 86/86, cab IRs 2,235/2,237
  plus all 45 DynaCabs (cabs via @bschmalz81401, #14), and 34 delay/chorus/
  multitap type references, all facts-only with citations.
- Simulator fidelity: async-write settle window (unsettled reads return
  pre-write state, like hardware) and undecoded-territory tracking (the sim
  names what no hardware session has verified instead of silently
  simulating it).
- Read-only tooling: preset inspector (tone report of any preset) and tone
  library harvester (voicing references from curated on-device presets;
  output stays local, never committed).
- Device snapshot resolves the active cab IR to the real cabinet it models.
- Honesty warnings: add_block warns that factory defaults are not a
  finished sound; bind_pedal warns its curve direction is unverified (#11).

### Fixed
- Same-row cable draws on grid row 2 (hardware-decoded encoding; the
  general formula silently drew nothing).
- Channel cache auto-population (empty cache silently collapsed every
  channel read to channel A).
- FM9 port handling: loud preflight on poisoned ports, context-manager and
  atexit cleanup, close() deadline (zombie processes held the MIDI port and
  corrupted later sessions).
- A failed add_block aborts the remaining plan instead of binding pedals to
  blocks that never landed.

### Added (2026-08-21 session)
- Tone library harvested: all 512 on-device presets captured as voicing
  references (local-only), plus a per-scene consistency audit that caught
  and fixed a systemic dry-scene staging bug across the setlist.
- Effect-type grounding: 34 delay/chorus/multitap names mapped from wiki
  sources; pitch type ordinals begun (wire-verified, human-in-the-loop).
- add_block verifies and self-repairs the downstream cable after
  shunt-replacement.

### Protocol findings (README "Protocol Contributions")
- Negative signed params are 16-bit two's complement on the wire
  (-12 = 65524). Pitch types: Dual Detune = 0, Dual Chromatic = 2.
- Shunt-replacement inherits the incoming cable only; the outgoing side
  can silently drop. Row-4 same-row cable draws follow the general
  formula. Shunts cannot be inserted; a unity Volume block is the
  pass-through workaround. Inserts are silently refused over the DSP
  budget.
- Row-2 same-row cable encoding; cable draw is idempotent (removal is a
  different, unknown message); 2-row diagonal draws do not register.
- Writes are asynchronous; unsettled reads return plausible stale values.
- Amp display-name query behavior differs by firmware (under investigation
  with @bschmalz81401, #15).
