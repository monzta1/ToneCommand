# Changelog

Notable changes to ToneCommand. Dates are UTC.

## Unreleased

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
