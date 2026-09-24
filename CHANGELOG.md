# Changelog

Notable changes to ToneCommand. Dates are UTC.

## Unreleased

### Fixed
- NO EM DASH REPO-WIDE, WHICH THE RULE ALREADY SAID. CLAUDE.md bans it
  everywhere, but enforcement was seven separate guards each carrying a
  hardcoded list of "the files this phase touched". Between them they never
  covered `docs/UI-REDESIGN-SPEC.md` (17) or
  `docs/CLAUDE-CODE-UI-IMPLEMENTATION-PROMPT.md` (5), and nothing would have
  covered the next new file either. Both docs are rewritten: label separators
  become colons, two parentheticals become parentheses, the stage rail becomes
  an arrow, and the two table placeholders become `-` and `none`.
- SOME OF THOSE ARE GLYPH CHANGES IN SPECIFIED ON-SCREEN TEXT, not only
  punctuation in prose: the stage rail, the TARGET / SCOPE / DESTINATION /
  RECOVERY rows and the Before/After placeholders all specify what a surface
  shows. That surface is proposed rather than built, and the shipped
  `ui/index.html` contains no em dash and renders an arrow between values, so
  the change contradicts nothing in the build. It is still a change to
  specified output and is recorded as one.
- THREE GUARDS WERE THEMSELVES THE VIOLATION. `test_ai_settings.py`,
  `test_site_build.py` and `test_splice_consent.py` asserted against a literal
  `"em dash"` character, so each one contained the thing it banned and a
  repo-wide check would flag the checks. They now spell it `chr(0x2014)`, as
  the four other guards and the inline assertion in `test_capture_intent.py`
  already did.

### Added
- `tests/test_no_em_dash.py`: one guard over every tracked text file, so a new
  file is covered by existing rather than by somebody remembering to extend a
  list. Verified by planting an em dash in a file none of the seven per-phase
  guards covered.
- IT FAILS RATHER THAN SKIPS ON ANYTHING IT CANNOT READ. A tracked file that
  is not valid UTF-8, or is tracked but not a readable file, is reported
  instead of passed over, because "we could not read it" and "it is clean" are
  different answers. That immediately surfaced three `.bin` fixtures the
  first, skipping version had been quietly dropping. Same reason `git` missing
  raises instead of skipping.
- THE THIRD-PARTY EXEMPTION IS THE QUOTED REGION, NOT THE FILE.
  `THIRD_PARTY_NOTICES.md` is scanned; only the fenced block under
  "Reproduction of that project's NOTICE (as required by Apache-2.0)" is
  exempt, because Apache-2.0 section 4 requires that NOTICE be reproduced and
  reproducing it means reproducing it. Excluding the whole file left this
  project's own prose in it unguarded. A test fails if the heading or fence
  moves, if the quoted block stops containing one, or if an em dash appears
  outside it.
- `config/fm9_catalog.json` is exempt whole, because it is copied verbatim
  from mcp-midi-control and `config/README.md` says to refresh from upstream
  rather than hand-edit. A test fails if that stops being true.

- `docs/WINDOWS.md`, the step-by-step Windows guide, is its own page with its
  own short link to share: **tonecommand.com/windows**. It was the Windows
  section of `docs/SETUP.md`, which now points at it, so there is one place to
  send someone who has never opened a terminal. It carries the
  `UnicodeDecodeError` a user hit before 1.5.3, with both ways out (download
  again, or `$env:PYTHONUTF8 = "1"` for that window), and it no longer calls
  Windows untested: the suite runs there on every change.

### Fixed
- The site's `ROUTES` did not know about the new page, so the README's and
  SETUP.md's links to `docs/WINDOWS.md` rendered as
  `.../blob/main/WINDOWS.md`: a path that does not exist, on the two pages
  most likely to be read by someone looking for it. Two tests in
  `tests/test_site_build.py` now fail on it: one pairs every short-URL doc
  with its route, the other builds the site into a temporary directory and
  checks every repository link it produced against the tree. That second one
  runs the build itself because `site/dist` is gitignored and CI never builds
  the site, so a test that read an existing `site/dist` would skip in the one
  place that gates a merge. `markdown` and `Pygments` moved into the `dev`
  extra for the same reason: CI installs `.[dev]` only, so a test whose
  import lived in the `site` extra failed the required check while passing on
  a developer machine that happened to have it.
- `docs/SETUP.md` states the Python 3.11/3.12 ceiling, the
  `TONECOMMAND_MIDI_BACKEND=supriya` way out and the #172 hardware pass again.
  Moving the Windows walk-through to its own page took those sentences with
  it, which `tests/test_midi_transport.py` requires that file to carry; they
  belong under Compatibility rather than inside one platform's guide.

## 1.5.3 (2026-09-22)

### Fixed (a Windows install could not start at all: #184, #186)
- `Path.read_text()` and `open()` without `encoding=` follow the machine's
  locale, which is cp1252 on Windows and UTF-8 here. `config/amp_models.json`
  carries curly quotes (the AC-30 note's "Cool"), whose UTF-8 bytes are
  undefined in cp1252, so `Registry()` raised `UnicodeDecodeError` at import
  and the app never started for a user on Python 3.12.10. Every text read and
  write now names `encoding="utf-8"`: 362 `read_text()`, 88 `write_text(...)`
  and the five `pathlib` `.open()` sites. Opens that are not text files
  (`os.open`, `wave.open`, `Image.open`, the urllib opener, MIDI ports) are
  untouched.
- `fm9/ai_settings.cliproxy_key()` called `os.getuid()`, which does not exist
  on Windows, so AI settings raised `AttributeError` there. The uid stays the
  seed wherever it exists, so a key already baked into a config file on macOS
  or Linux keeps its value; Windows derives from the account name.

### Added
- `tests/test_text_encoding.py` fails on any new encoding-less text read or
  write, proves the shipped config JSON is UTF-8 with at least one file
  cp1252 cannot decode, and loads the registry with the locale encoding
  forced to cp1252, which is the reported failure reproduced.
- CI runs the suite on `windows-latest` as well as `ubuntu-latest`. The
  matrix runs as the `suite` job and a small `tests` job gates on it, so the
  one required check on `main` keeps its name. A Linux-only matrix could
  never have seen this class of bug.

### Known, not fixed here (#186)
- The settings file and the TONE3000 token file are written `0o600` and
  re-tightened on save. Windows ignores POSIX modes, so on Windows both are
  readable by other local accounts until an ACL replaces the mode; the two
  assertions are skipped there with that reason.
- `tests/test_planner_grok.py` runs a shebang script as a fake backend, which
  Windows does not honour, and one HeadRush client test fails on Windows only
  for reasons not yet established; both are skipped there.

## 1.5.2 (2026-09-21)

### Fixed (the bundled app's CI build died on import, 2026-09-20: #175 follow-up)
- `numpy` was an optional extra (`audition`) while `fm9/reamp.py`,
  `capture.py`, `measure.py`, `sound_check.py` and `tone_match.py` import
  it at module level and `server.py` imports them unconditionally. The
  bundle workflow installs with `pip install .` and no extra, so the app it
  froze had no numpy and died on the runner's smoke test; every developer
  venv here had the extra, which is why nothing noticed locally. numpy is
  a core dependency now; the `audition` extra stays, empty.
- `server.py` and `fm9/health.py` import from `tools/`, which was not a
  packaged package; it is now (with an `__init__.py`), so a wheel carries
  the two modules the app needs. `tests/test_packaging.py` checks that every
  repo package the server imports is packaged and that every module-level
  third-party import is a core dependency; both fail without the fixes.
- Known, not fixed here: a non-editable `pip install .` still cannot run
  the server from outside the repo, because `config/`, `ui/` and
  `recipes/` are repo-root data the wheel does not carry. The supported
  paths remain the editable install the docs describe and the bundled app
  (which collects them). Packaging the data directories is filed
  separately.

### Added
- A self-contained unsigned macOS `ToneCommand.app` bundle with Python inside,
  a simulator smoke test, and a tag/manual GitHub Actions packaging workflow.
  Windows builds, signing, and notarisation remain later chunks.

### Docs
- `docs/HEADRUSH-HARDWARE-FINDINGS.md` Finding 5: the unit snaps the display
  value to the published grid and stores the result as float32, so a
  read-back equals the write only when the display value was already on the
  grid (#167, #173, #174).
- AGENTS.md and CLAUDE.md: main is protected and lanes land through a PR
  (#178); step 2 points at the engine's own `handsoff playbook` before the
  local KB (#180).

## 1.5.1 (2026-09-20)

### Added (reference tone-match by measurement, 2026-09-20: #105 G6)
- `fm9/tone_match.py`: both spectra measured the G2 way (the reference at
  any rate; its loudness is not a target), the build's band deltas named
  against the reference ("4.6 dB less body than the reference"), and for
  each band with a gap of at least 1.5 dB one amp knob and a DIRECTION
  from the `reference_match` table in `config/sound_policy.json` (the FM9
  amp block's own controls: body to bass, presence to presence, bite to
  treble, air to high cut, rumble to low cut, low control to depth), as a
  first step of 1.0 on a knob or 20 Hz on a cut, clamped to the range. The
  magnitude is never computed: no dB-to-knob calibration has been
  measured and none is invented; the re-measure loop (G5) verifies the
  move. Proven with a reference made by EQ-ing the unit's own capture: the
  proposed directions reverse the EQ.
- `GET /api/references` lists the references folder
  (`TONECOMMAND_REFERENCES`, default `~/.tonecommand/references`);
  `POST /api/tone-match {build, reference}` answers the match and a
  proposal in the health scan's fix shape (the knob's current value plus
  the step) for showPlan, so Confirm is the only way on to the unit;
  MATCH REFERENCE sits beside SOUND CHECK; `tools/measure.py <build>
  --reference <wav>` prints the same. Both routes read only.

### Added (TONE3000 sign-in, the documented OAuth flow, 2026-09-20: #88 D2)
- `fm9/tone3000_auth.py`: TONE3000's OAuth 2.0 with PKCE as their API
  documents it (`api/v1/oauth/authorize` with S256 and state, then
  `api/v1/oauth/token` for the code exchange and the refresh), the
  publishable key from `TONE3000_PUBLISHABLE_KEY`, tokens in
  `~/.tonecommand/tone3000_tokens.json` at mode 0600, refreshed a minute
  before they expire. The module never logs; HTTP is injected and the
  default reaches www.tone3000.com only.
- Routes: `/api/tone3000/login` (the authorize url; one pending state and
  verifier), `/api/tone3000/callback` (state verified, an error stores
  nothing, the code exchanged, then back to the app), `/api/tone3000/status`
  (signed in and expiry, never a token), `/api/tone3000/logout`, and
  `/api/tone3000/load?tone_id` for TONE3000's `load_tone` flow, which
  verifies the account's access to a tone and lets the player browse a
  replacement when it is unavailable. Settings has the SIGN IN / SIGN OUT
  row; the redirect URI is `http://127.0.0.1:8909/api/tone3000/callback`.
- Every player-facing TONE3000 fetch runs under the signed-in token:
  `recipe_capture.key_from_env` prefers it over the secret key; a capture
  the account cannot reach stays `not_yours` (link, nothing fetched) and
  now carries `replacement_url`, which the recipes browser logs. Paid or
  private is what TONE3000 answers to the player's own token.

### Added (catch and propose a fix, human-confirmed, 2026-09-20: #104 G5)
- `fm9/sound_check.py` `propose(balance, levels)`: each measurable balance
  finding (G3's intent_target rules, with a baseline) becomes ONE move in
  the action vocabulary, `set_param` on that scene's `OUTPUT_SCENEn`: the
  current trim plus the LU needed to reach its target (clean and rhythm on
  the rhythm median, a lead 2.5 LU above, anything over the cap down to 3),
  rounded to 0.5 dB, clamped to the trim's -20..20 with the shortfall said
  and the rulebook's amp-level caveat named. One rhythm median for every
  target, so moves cannot fight; a scene appears once (the cap rule wins);
  no baseline or a style finding gets no move. The fixes use the health
  scan's shape (`how: actions`), so the page hands them to `showPlan` and
  Confirm and `/api/apply` are the only way anything reaches the unit:
  nothing here sends.
- `rounds(state, balance, proposal)`: measure, propose, confirm, re-measure,
  capped at three rounds; ends clean when nothing measurable remains, or
  by the cap with "after 3 rounds these remain: ...". One state per loaded
  preset, reset on a preset change. Proven on the simulator with a fake
  recorder whose loudness follows the sim's own trims: a confirmed move
  lands to the dB and round two is clean; a masked scene (the trim does
  nothing, the amp is the bottleneck) ends by the cap, reported, not
  chased.
- `POST /api/sound-check {captures}` measures captures under the captures
  folder and answers balance, proposal and state; `POST
  /api/sound-check/remeasure {scenes}` records each scene through the USB
  path under `routing.temporary` (restored, journaled) and answers the
  next round; both refuse under GIG LOCK. SOUND CHECK sits under the
  health scan's findings, with PROPOSE going through the plan path. The
  live run is the next rig session's.

### Verified against a Core (#167 fix, 2026-09-20)
- THE SYMPTOM IS GONE ON THE UNIT. `Amp.TremSpeed` at wire 0.25 reported
  `ok=False` on a Core three hours earlier and reports `ok=True` now, with
  the displayed value unchanged at `1.48 Hz`. 8 passed, 0 failed.
- `set_param_display(5.19)` still reports `ok=True`. That request lands ON
  the grid, so the unit stores it exactly; a uniform tolerance window would
  have stopped requiring that, and this run is the evidence the prediction
  did not.
- The restore warning from the previous run is also gone, and the reason is
  the model: every value the device HOLDS is the image of a grid point, so
  writing one back is a fixed point. Five parameters restored, no note.

### Fixed (the read-back is predicted, not tolerated, 2026-09-20: #167)
- `_write_verified` called a write a failure whenever the unit quantized it.
  On `Amp.TremSpeed` that was every wire value tested, three for three: the
  device converts a written wire value to display, snaps the DISPLAY value to
  the published grid, converts back and keeps float32, so a write it HONOURED
  read back as a different float.
- IT NOW PREDICTS WHAT THE UNIT WILL HOLD AND STILL COMPARES EXACTLY.
  `_expected_read_back` runs the write forward through the unit's own
  arithmetic; `_write_verified` gains an `expect=` and nothing else changes.
  There is no tolerance anywhere, so a value the unit discarded still fails.
  The result carries `held` when the two differ, because a caller that plans
  against what it wrote would be planning against a number the device never
  had.
- THE ANCHOR IS THE EIGHT WRITE/READ PAIRS #167 MEASURED ON A CORE, across
  Linear and Squared and grids of 1.0, 0.1 and 0.01. The prediction reproduces
  all eight BIT-EXACTLY. A test comparing the adapter against the simulator
  would only be self-consistency, because both now use the same vendor table.
- THE PUBLISHED GRID IS A FLOAT32 AND COST TWO WRONG VERSIONS OF THIS FIX.
  A grid the vendor wrote as 0.01 arrives as 0.009999999776482582; snapping
  with that literal puts `Amp.TremSpeed` at 0.33299559354782104 where the unit
  holds ...62335014343. `tapers.snap_to_grid` recovers the decimal at
  float32's ~7 significant digits, and lives there rather than in the adapter
  because the simulator needs the same arithmetic.
- A prediction that cannot be made - no table, no grid, an unknown curve -
  falls back to comparing what was sent, which is the behaviour that shipped.
  The display methods refuse in that situation because a converted number
  would be a fiction; a write must not, because the unit would have accepted
  it.
- NOT because a tolerance is unsafe. That argument does not survive the
  device: the unit can only hold a grid point, so a half-grid window admits
  exactly one value. The reasons that do hold: a uniform window would stop
  requiring an ON-GRID write to read back exactly when the unit returns those
  exactly; a window needs the curve anyway to map the grid into wire space;
  and a prediction can report what the unit holds. A mutation replacing the
  exact comparison with a window still passes this suite, and no test here can
  tell them apart without simulating a device that violates its own
  quantization.

### Fixed (the simulator did not quantize, so no test could see #167)
- `HeadrushSim` stored every write verbatim. The device does not, which is why
  the suite was green while a real Core reported `ok=False` for writes it had
  honoured: the double was modelling a device that does not exist.
- It now converts, snaps and converts back on the way in, and reproduces all
  eight values a Core held in #167 bit-exactly. One existing test changed:
  `test_writing_a_display_value_still_verifies_the_wire_value` asserted the
  sim held `approx(0.5)`, which was asserting the double's fiction.

### Added (HeadRush display conversion, 2026-09-19: #130)
- `HeadrushAdapter` TAKES AN OPTIONAL CURVE TABLE. `tapers=` is opt-in and
  defaults to None, so an adapter built the way every existing caller builds
  one refuses display conversion exactly as before. With a table,
  `get_param_display` and `set_param_display` work.
- THE REGISTRY'S REFUSAL IS UNTOUCHED. It describes the API, which still
  publishes an opaque `normalizeAlgo` and no formula, and `tapers.py` says the
  refusal "is still correct about the API and is left alone". The adapter is
  the right place for the other kind of knowledge, because it can carry the
  provenance with every value.
- `get_param_display` RETURNS A `DerivedDisplay`, NEVER A BARE FLOAT: value,
  the unit's own formatting applied, the curve's name, where the maths came
  from, and `api_readable=False` on every instance. `get_param_wire` returns a
  plain float because the unit sent that float, and the asymmetry is the
  point: a converted number must not be loggable or plannable as though the
  device had reported it.
- `set_param_display` CONVERTS AND THEN WRITES THROUGH THE SAME VERIFIED PATH,
  so the read-back still compares wire values. Only the caller's units change.
- `UnknownTaper` and `NotConvertible` are not caught. An id the table has never
  seen means the firmware publishes a curve the table was not built against,
  and scaling linearly anyway would silently mis-read every value of that
  parameter.

### Verified against a Core (HeadRush display conversion, 2026-09-20)
- `tools/verify_headrush_display.py` RAN AGAINST A CORE at 5.1.0.2a63755 on a
  `##HRB` preset: 8 passed, 0 failed. It is the first thing to construct
  `HeadrushAdapter(..., tapers=tapers.load())` against firmware at all, which
  every test here does only against the simulator. Transcript and findings in
  `docs/HEADRUSH-DISPLAY-VERIFICATION-168.md`.
- WHAT THE SCREEN ROWS ARE. The six readings came from the web editor the unit
  serves, which the owner attests matches the device - not from the Core's
  front panel. `tapers.py` was built from that editor's own bundle, so those
  rows confirm a chain (we reproduce the editor, the editor matches the unit)
  rather than reading the hardware independently. #130's `hardware_check` rows
  say "taken off a Core's screen"; these are not those and do not claim to be.
- #167 REPRODUCED LIVE THROUGH THIS PATH: `Amp.TremSpeed` at wire 0.25
  reported `ok=False` while displaying the correct `1.48 Hz`. Every earlier
  observation was through the raw wire API.
- AND #167 IS NARROWER THAN IT WAS STATED. `set_param_display(5.19)` reported
  `ok=True`, where this changelog predicted failure: 5.19 is already ON the
  0.01 grid, so the unit had nothing to snap. The rule is not "a quantized
  parameter always reports failure" but "a request between grid points does".
- No wire value can restore such a parameter exactly - writing back the `0.5`
  `Amp.TremSpeed` held yields `0.5001265406608582`, which displays the same.

### Checked against hardware readings (HeadRush display conversion)
- NO UNIT WAS TOUCHED BY THE TESTS. The readings are a Core's, recorded in
  the #130 and #167 sessions (firmware 5.1.0.2a63755, a `##HRB` test preset);
  what is new here is that the adapter is driven over them. Calling that
  "verified on hardware" would claim a session that did not happen, so it
  does not.
- The six `hardware_check` rows in `config/headrush_tapers.json`, readings
  taken off a Core's screen, are now a parametrised test: the adapter
  reproduces all six as formatted text, `75 %` through `1.48 Hz`.
- THE DEVICE'S OWN ARITHMETIC AGREES WITH THE TABLE. The unit converts a
  written wire value to display, snaps the DISPLAY value to the published
  grid, and converts back (#167). Reproducing the float it ends up holding
  runs the curve forwards and backwards through that quantisation, and it
  matches to the last bit on `Amp.TremSpeed`, whose curve is Squared. A
  linear scale cannot produce those floats, which a second test asserts so the
  first is evidence about this table rather than arithmetic any curve
  satisfies. This is stronger corroboration than a photographed screen,
  because a misread digit cannot produce it.

### Changed (third follow-up review, 2026-09-20)
- Two nits, both UNANIMOUS across the local reviewer's three samples, which
  is the signal worth acting on from a model whose single-sample findings are
  usually wrong. `_must_be_continuous`'s docstring said the only thing
  standing in the way of a selector being converted "would be a test", while
  the guard it documents is code; it now says what each half does, because
  the guard is the behaviour and
  `test_a_selector_is_not_dragged_onto_the_continuous_path` is the warning
  that fires if the registry-wide fact ever stops being true.
- `test_a_selector_never_reaches_the_device_to_be_refused` is now
  `test_the_guards_refuse_before_any_call_reaches_the_device`: it is about
  the guards running before the transport, not about selectors.

### Fixed (second follow-up review, 2026-09-19)
- A TEST THAT COULD NOT FAIL FOR THE THING IT WAS NAMED AFTER. The check that
  the display methods refuse BEFORE touching the device built the plain
  simulator opener (a stray `_converting(reg, )` passed no kwargs, so the
  recording opener was never installed) and then skipped its call-count
  assertion when there was nothing to count. Moving the guard back below the
  read would have left it green. It now asserts an empty call list on the
  recording opener unconditionally, on both the read and the write path, and
  was confirmed to fail with the guard moved.

### Changed (follow-up review, 2026-09-19)
- THE SELECTOR GUARD MOVED OUT OF THE TEST AND INTO THE METHODS. The first
  round answered "a selector cannot reach the continuous path" with a test
  asserting no parameter carries both `options` and a display range. That is
  a true statement about today's schema and the wrong place for the
  invariant: a firmware that grew one would have had its ORDINAL run through
  a 0..1 taper, with an assertion about the schema as the only thing in the
  way. `_must_be_continuous` refuses a selector by name, in both methods.
- The guards run BEFORE the device is read, so a spec that was never
  convertible does not cost a round trip to find that out.
- `DerivedDisplay.api_readable` is `field(init=False)`. It described the
  invariant and did not hold it: a caller could construct one claiming the
  unit said the number. Construction, `replace()` and assignment all refuse.
- `tapers=` IS CHECKED AT CONSTRUCTION, not merely annotated. The annotation
  `TaperTable | None` was written up as though it were a runtime guard, which
  it is not: `HeadrushAdapter(..., tapers=object())` still built and failed
  later inside a `getattr`. It now raises `TypeError` immediately, because an
  object that merely answers to `to_display` and `to_wire` would be
  converting with a curve nobody can name the provenance of.
- The `_formatted` fix from the first round was unguarded, which is how it
  got there. A test now pins a device format that cannot apply and asserts
  the unit survives.
- `NotConvertible` is asserted on a fabricated spec, and a second test says
  why that is not a cheat: NO parameter this firmware publishes reaches a
  non-finite value at either end of its own range, so there is no real one
  to use. If that ever stops being true, the test fails and names it.

### Changed (review of the display conversion, 2026-09-19)
- THE METHOD DOCSTRING CLAIMED MORE THAN THE CODE DOES. It said "nothing
  about the check weakens", which is true and beside the point: the check was
  already wrong on a quantized parameter (#167), and this is the first API
  that invites a caller to write in display units, so it is the first one
  obliged to say so. `set_param_display` now states that `ok` is exact
  equality against the read-back, that False does not mean the write failed
  until #167 is fixed, and that `get_param_display` is how to see what the
  unit actually holds.
- The module's `WHAT IT DOES NOT PRETEND` contract still said both display
  methods refuse. A caller who reads the adapter's contract rather than the
  two methods would have been told the opposite of what the opt-in path does.
- `DerivedDisplay` IS A FROZEN DATACLASS, NOT A NAMEDTUPLE. A NamedTuple is a
  tuple, so `got[0]` and `value, *_ = got` handed back exactly the bare float
  the type exists to withhold, and the test that guarded it (`not
  isinstance(got, float)`) could never have failed. Indexing and unpacking now
  raise, and the test asserts that instead.
- `_formatted`'s fallback for a device format string that will not apply
  dropped the unit, which the no-format path keeps.
- The round-trip test asserted `approx(..., abs=1e-9)` while the changelog
  claimed a match "to the last bit". It is exact, so it now asserts exact
  equality.
- Three cases the tests did not reach: a read that came back absent (refused,
  because 0.0 is a real value on every one of these curves), `NotConvertible`
  (named as deliberately uncaught and never asserted), and a selector, which
  cannot be dragged onto the continuous path because no parameter in the
  registry carries both `options` and a display range - asserted over the
  whole registry, so it fails if one ever does.

### Known issues
- `set_param_display` on a parameter the unit quantizes reports `ok=False` for
  a write the unit honoured. That is #167 and not this conversion: the write
  path compares the read-back with exact equality, and on `Amp.TremSpeed`
  every wire value tested reports failure. The conversion is correct and the
  displayed text is right; the flag is wrong. Fixing it belongs in
  `_write_verified`.

## 1.5.0 (2026-09-20)

### Added (a MIDI transport seam with a second binding, 2026-09-20: #172)
- `fm9/midi_transport.py` is the one place MIDI ports are opened.
  `TONECOMMAND_MIDI_BACKEND` picks the binding: `auto` (default: mido over
  python-rtmidi when it imports, else supriya-midi), `mido`, or `supriya`;
  an unavailable backend is refused in one line naming what to install.
  Both hand the device layer the port shape the simulator already uses
  (`iter_pending()`, `send(mido.Message)`, `close()`); mido stays as the
  message class. The supriya adapters open the port by name, enable sysex,
  size the queue for a 2,100-frame bulk read, and encode sysex, program
  and control change; proven on a fake port pair with the simulator's
  core answering behind it, including a status dump, a bulk read and the
  never-brick guard refusing a frame before any port sees it.
- pyproject: python-rtmidi for Python below 3.13, supriya-midi 26.9b0 for
  3.13 and newer, by environment marker. `requires-python` keeps its
  `<3.13` ceiling until the supriya path has its hardware pass on the unit
  (#172 REQ-004); a 3.11 or 3.12 install gets the same packages and the
  same default backend as before. `server.rescan_midi` reloads mido's
  backend only when mido is the backend, and the once-a-second presence
  check (`_fm9_port_present`) enumerates through `midi_transport.port_names`
  so a supriya install reports the unit the same way (review F1.1).

### Added (the measurement ears, 2026-09-20: #101 G2, #102 G3, #103 G4)
- `fm9/measure.py`, numpy only: a capture is measured only after
  `validity` passes (too short, digital silence, clipping at the endpoint,
  a dropout of exact zeros with signal on both sides; lead-in zeros from
  USB latency are not a dropout), on active windows only. Then the
  spectrum as band ratios over the six descriptive regions of
  docs/SOUND-CHECK-DESIGN.md 10.2 (each a dB offset from the whole, so
  level cancels), a centroid as a secondary number, loudness per ITU-R
  BS.1770-4 (K-weighting at 48 kHz, 400 ms blocks, absolute and relative
  gates, integrated LUFS; a -23 dBFS 1 kHz tone reads -23.0, the EBU
  conformance case) with a short-term distribution and no LRA on a short
  clip, stereo (L/R correlation, mid/side, inter-channel level, mono
  fold-down loss) and dynamics (crest, short-term spread). Every result
  carries the design 3.5 checker contract: status, coverage, evidence,
  missing facts. `compare` names its baseline in every line.
- `config/sound_policy.json`, versioned: the ONLY source of enforced
  numbers. Enforced are the balance rules the rulebook states (rhythm
  scenes within 1 LU, leads 2 to 3 LU above, no scene more than 4 LU above
  the rhythm median, cleans not below rhythm) and the definitional mono
  check (correlation at or above 0.98 within 0.5 dB); style rules are
  listed and never pass/fail; the acquisition numbers are declared there
  too. Prose is never parsed. Absolute spectral floors are not enforced
  (the #50 lesson).
- `scene_balance` applies those rules against the rhythm scenes' median
  and says when there is nothing to judge against; `fm9/sound_check.py`
  `capture_scenes` records the test capture per scene and returns to the
  origin scene whatever happens (simulator-proven; live proof next rig
  session). `POST /api/measure` and `POST /api/measure/balance` read
  captures under the captures folder only and write nothing;
  `tools/measure.py` prints the same from the terminal.
- Fixtures: this morning's captures from the unit (the test signal through
  preset 138 and the noise floor).

### Fixed
- `capture.record` named files to the second, so scenes captured within
  one second overwrote each other; the scene is in the name now and a name
  is never reused.

## 1.4.1 (2026-09-20)

### Fixed (install on Python 3.13 and newer failed with a compiler trace, 2026-09-20)
- A Windows player on a fresh python.org Python hit "Preparing metadata
  (pyproject.toml) did not run successfully ... python-rtmidi ... Unknown
  compiler(s)": python-rtmidi 1.5.8 ships prebuilt wheels for CPython 3.8
  to 3.12 only, on every platform, so on 3.13 or newer pip builds it from
  source with meson and needs a C++ toolchain. `requires-python` is now
  `>=3.11,<3.13`, so pip answers in one line naming the Python it wants;
  the Windows guide installs 3.12 from the releases list (`py -3.12 -m venv`)
  and lists the error under "If something goes wrong"; the README says the
  same for every platform.

### Added (Gate 0 proven on the unit, and the capture method, 2026-09-20: #56, #100 G1)
- `fm9/reamp.py`: the FM9 as a USB audio device through sounddevice (found
  by name, 48 kHz and 8 in / 8 out asserted), `replay_and_record` (mono DI
  on one computer output, the return on named inputs, peak capped at
  -12 dBFS, ten seconds at most, one run at a time, the device lock held so
  audio never overlaps a MIDI write) and `distinguish` (silence below
  -60 dBFS RMS, loopback above 0.98 normalised cross-correlation at any
  lag, else processed).
- `fm9/routing.py`: Input 1 Source and Digital Input Source (GLOBAL 72 and
  73, effect id 1) read through bulk_read; `temporary` applies a change
  under a journal and restores it in `finally` with a settled, retried
  read-back (#169's rule), keeping the journal if a restore fails;
  `restore_outstanding` puts a dead process's change back, and the server
  calls it the first time it holds the unit (`_restore_routing_journal`
  inside `get_fm9`, before any other work; a failure is logged and the
  journal kept). No global is ever written to an ordinal the unit was not
  observed holding, a journal's 'before' included; the observed table is
  `config/reamp_observed.json` (Input 1 Source 0 = ANALOG, 1 = DIGITAL;
  Digital Input Source 1 = AES, 2 = USB), loaded at import
  (`load_pinned`, `TONECOMMAND_REAMP_OBSERVED` moves it).
- `fm9/capture.py`: the three capture methods (`test`: 1 kHz at -18 dBFS
  then a 20 Hz to 20 kHz log sweep, 4 s; `playing`: 6 s, prompted;
  `silence`: 4 s), `record` writing a 48 kHz stereo WAV plus a sidecar
  naming the method, channels, rate, preset, scene and routing.
- `tools/reamp_spike.py`: the Gate 0 steps one at a time (device, routing,
  observe, replay, restore-test, journal).
- Proven on the FM9 (firmware 11, macOS, one process holding MIDI and USB
  audio): device at 48 kHz 8/8; output 5 in, inputs 1/2 out; the return is
  PROCESSED under DIGITAL/USB and SILENT under ANALOG/AES; routing restored
  after success, a forced exception and a process restart via the journal;
  no flash touched. The 0x1F name query is stale for GLOBAL params (labels
  come from the panel). Not proven: Windows channel map, disconnect
  mid-change. Written up in docs/SOUND-CHECK-DESIGN.md under Gate 0.
- The simulator has a GLOBAL block (effect id 1, one row, outside any
  preset) so routing tests run on it.

### Fixed (the repoint read-back raced the settle window, 2026-09-20: #169)
- `gallery_install.repoint` wrote a Cab block value and read it back at
  once, inside the unit's settle window (#12). It passed here and on CI
  only because parsing a 2,043-frame CABINET bulk read takes about 100 ms
  on those machines and because the simulator counted the channel query
  inside `get_param_wire` as a write, refreshing its snapshot; on a faster
  machine it read the old value every time (reported by @bschmalz81401 on
  #169 and #168). `repoint` now settles and retries like the verified
  setters (`_read_back`, 4 x 0.15 s), the simulator's classifier no longer
  counts a bank or channel QUERY as a write, and a new test widens the
  settle window to 0.4 s so an unsettled read-back fails on any host.
  The opening read of `repoint` (the one that decides which channels to
  touch) settles too: on a slow CI worker it read the block before
  channel D's last write had landed and skipped that channel's Legacy
  switch. `tests/test_sim.py::test_bypass_is_per_scene` had the same shape (a
  bypass query read at once after the write) and now settles, as
  KNOWN_QUIRKS rule 1 has said since August; rule 3 there records this one.

## 1.4.0 (2026-09-20)

### Added (a recipe uses a capture by reference, 2026-09-20: #153 I10)
- `fm9/recipe_capture.py`: a recipe may carry one `capture` field
  (source TONE3000, tone id, model id, page url, licence, the sha256 of
  the file the sharer had, and `stands_for`, the amp model it builds with
  otherwise); `serialise` makes one from a .nam and its ids, `validate`
  refuses in one line any other source, a bad id, an off-site url, a
  malformed hash, a stand-in not on the amp roster, an extra key, or
  anything that could be the file itself (bytes, a `data:` URI, a long
  base64 run). `/api/recipes/save` refuses such a recipe (400) before it
  is saved or queued.
- `resolve` answers one of four for the recipient: `available` (the hash
  is in the library, or the model record and then the file were fetched
  from www.tone3000.com under the recipient's OWN `TONE3000_SECRET_KEY`
  and hashed to the recipe's sha256; the bytes go through intake in
  memory and are never written), `not_yours` (no key, 401, 403 or a
  private tone: the link, nothing fetched), `missing` (404 or a different
  file under that id now), `unreachable` (timeout, 5xx, a malformed
  record, an off-site url). All but the first build with `stands_for` and
  the line names the amp. Confirmed live against TONE3000's api/v1 on
  2026-09-20: `/models/<id>` carries `model_url`, `/download` needs the
  file name, both need the caller's key, and a tone has `is_public` and
  `license` and no price field.
- `/api/recipes/plan` takes `known` (the capture library's sha256 list,
  as intake does) and answers `capture: {status, line, link, sha256,
  stood_for}`; the recipes browser says a recipe uses a capture and logs
  the line with the plan. docs/RECIPES.md documents the field.

### Added (installed artist packs as a reference, 2026-09-20: #159 J6)
- `fm9/installed_packs.py`: every gallery install (#155) is recorded
  (`~/.tonecommand/installed_packs.json`, `TONECOMMAND_INSTALLED_PACKS` to
  move it): entry id, artists, year, label, preset name, store slot, cab
  slots, and EVIDENCE read from the pack's preset as it landed (the amp
  model with gain, bass, mid, treble, master and presence; the cab; the
  drives; delay and reverb presence), each record tagged artist, year and
  `pack file`, with a closed settings shape per kind (an amp record always
  carries all six knobs, null when unreadable; a cab record its bank and
  type ordinals; the rest nothing) that `validate_evidence` enforces. `find` resolves an artist phrase with the Artists shelf's
  rules (whole word, full name first, newest year, two artists is a
  question); `artist_words` drops possessives and the pack/rig/tone words
  ("Devin's" is Devin).
- Compare (#68) takes an installed pack as a source: `pack:Devin
  Townsend` or the bare name, tried after scenes, snapshots and designs.
  The server snapshots the edit buffer, selects the pack's slot, refuses in
  one line if the slot no longer holds the pack's preset, captures, selects
  your preset back and restores the snapshot; parameter, bypass and channel
  edits come back, and a block placed or removed unsaved is NAMED in the
  label ("WAH 1 was placed unsaved and is gone; place it again") rather
  than silently lost. Refused under GIG LOCK, and refused before any
  select when the unit does not say which preset is loaded (nowhere to
  come back to). The unresolved-source line
  now names installed packs among the kinds it tried.
- The planner's reference gains an INSTALLED ARTIST PACKS section, read
  from the record at request time (the static reference stays cached),
  with a heading that says these are block choices read from the file and
  not the artist's words.
- `/api/gift-of-tone/install` answers `installed_pack` (id, label, how
  many evidence records); a record that cannot be written is said in the
  line and never fails an install already on flash.

### Added (the Artists gallery, one click installs a pack, 2026-09-19: #155 J2, #164)
- `fm9/gallery_install.py`: `plan` decides where everything goes from what
  the unit reports and the two whitelists before anything is written: a
  cab goes to the bundle map's slot when that slot is in
  `TONECOMMAND_CAB_SLOTS` and reads `<EMPTY>` (or already holds the cab by
  name, then it is kept), else to the lowest whitelisted slot that reads
  `<EMPTY>` (#164); the preset goes to an empty whitelisted store slot
  when there is one, else to the lowest whitelisted slot (the whitelist is
  the slots the owner marked safe to overwrite) and the line names the
  preset it replaced. Refusals are one line: no store slots configured,
  no free cab slot, effect blocks only, no FM9 preset. `execute` performs it
  through the existing guarded primitives, in order: cabs
  (`install_user_cab_slot`, name-verified), the preset into the edit
  buffer (`FM9.load_preset_buffer`, the dump-plus-rename half split out
  of `install_preset`, no store), the Cab block repointed there when a cab
  moved (every `CABINET_TYPEn` on every channel whose bank is USER and
  whose value is the old slot, read back per channel; each such channel
  also switched to Legacy type, `CABINET_MODE` = 0, because a
  pre-Dyna-Cab pack preset loads as Dyna-Cab on firmware 11 and its user
  IR is never heard otherwise; 0 = Legacy and 1 = Dyna-Cab were pinned by
  a before/after read of the block around one FM9-Edit save), then ONE
  `store_preset` and a `select_preset` name read-back. It stops at the
  first failure and says what landed.
- Learned on the unit, recorded in kb/PROTOCOL.md: FM9-Edit's Cabs
  manager lists only cabs FM9-Edit itself wrote; slots written by Cab-Lab
  or ToneCommand show `<EMPTY>` there even though the unit's own name
  read returns the name and the IR plays. Do not use that list as a check.
- `POST /api/gift-of-tone/install {id}`: GIG LOCK 423, the J3 gates 409,
  effect-blocks-only 409 before any download, fetch and verify 502, the
  plan's refusals 409, else `{ok, line, store_slot, cabs: [{name, slot,
  editor, moved_from}], repointed, preset, read_back}`. The Storage
  drawer has an ARTISTS section: a card per entry the unit can take with
  one INSTALL button (effect-blocks-only entries say so; no device says
  installs need the unit); the click shows the line.

### Fixed (test audits caught up with this evening's routes, 2026-09-19)
- `tests/test_device_handle.py`: `read_user_cab_name` (fn 0x01 sub 0x4B,
  #155) is listed under FM9_ONLY with its reason; the live verify of #155
  on main failed on that one orphan.
- `tests/test_capability_gates.py`: `/api/gift-of-tone/install`,
  `/api/captures/intake` and `/api/axechange` are in the request table;
  `api_captures_intake`'s base64 except is in the audit (84 blocks, 35
  re-raising, 49 unreachable).

### Added (paste an Axe-Change link, 2026-09-19: #160 J7)
- `fm9/axechange.py`: one detail link (detail.php?preset=<id> on
  axechange.fractalaudio.com, nothing else accepted), that page's details
  block read into name, author, product, firmware, setup, description and
  the rest, shown as one line; a page without the block, or without a
  Name and a Fractal Product, is "could not read that page" and nothing
  else. The product is checked against the connected unit and the
  firmware by major against the unit's label with J3's wording; the
  preset is fetched from download.php on the same host, validated as a
  preset file, cached by id, and handed to the guarded install
  (`/api/install`: whitelist, load, read-back). No crawling, no search,
  no catalog of Axe-Change. `POST /api/axechange {url}`; the command bar
  sends a pasted link there and shows the install row.

### Added (bring your own captures, the intake half, 2026-09-19: #149; failure lines: #150)
- `fm9/nam_intake.py`: one `.nam` file, several, or a folder (walked for
  `.nam`, anything else skipped by name) go through I1 and come back as
  one honest line each (what arrived, or the not-on-file version);
  duplicates by sha256, within the drop or against the library the page
  remembers, are reported once and never taken in twice; captures of one
  amp (same gear make and model on file) form a set that maps to channels
  A to D of one block when four or fewer and to scenes when more, in gain
  order (clean, the crunch family, hi_gain) when every member carries a
  tone_type and in file order otherwise; mixed amps stay separate, lone
  ones are "added to your library, say the word and I'll build with it".
  `POST /api/captures/intake {files: [{name, data}], known: [sha256]}`
  answers the records, sets with their mapping, duplicates and the line;
  the composer accepts dropped `.nam` files and shows the line. Nothing
  reaches the unit: installing is I4's (#147).
- `fm9/capture_failures.py`: the five failure paths in one line each that
  says what was done instead: no suitable capture (the model), too heavy
  (a lighter variant when offered, else the model; the verdict is I0's,
  passed in), no NAM support on the unit (the model), gig gate (the
  existing refusal word for word), read-back mismatch (stop, report,
  never retry). `guarded_install` runs a plan in order and stops at the
  first install the unit does not read back, so a build is never left
  half-applied silently.
### Added (ToneX on the capture primitive, read-only, 2026-09-19: #163)
- `devices/tonex/`: the pedal on K1's `CaptureSlots`. `frames.py` is the
  serial frame decoder moved out of `tools/tonex_decode.py` (which now
  re-exports it): HDLC unstuffing, the X-25 FCS check, the tag walk.
  `adapter.py` declares `capabilities()` with `plays_captures=True` and
  `capture_capabilities()` as `('.tmodel',)`, 128 slots, an empty
  whitelist; `list_captures()` names all 128 programs (bank N, footswitch
  A/B/C = PC N*3+0/1/2) from the pedal's own 0x0204 preset dumps (name and
  category); `install_capture` and `remove_capture` refuse in one line
  naming #27 and invariant 0 before any frame exists. The rest of the
  device contract is there honestly: reads answer from the frames, every
  write refuses as read-only before any transport, and there is no method
  that sends. Frames come through a source: recorded frames in tests
  (`tests/fixtures/tonex_presets.json` with the 128 factory names and
  categories plus two raw frames; the full local capture set when
  present), the pedal's port behind `TONECOMMAND_TONEX_PORT` (read-only,
  never in tests). `tonex` is a device kind the picker offers only when
  that or `TONECOMMAND_TONEX_SIM=1` is set.
- Still open on #163: acceptance 2, the pedal's own list read against the
  adapter with the ToneX plugged in.

### Fixed (gate audit on main, 2026-09-19)
- `tests/test_capability_gates.py` had four failures on main since this
  evening's #156/#157/#158 routes: the three routes are now in the request
  table, the world fixture serves the local Gift of Tone catalog instead
  of letting the network tripwire surface as a 500, and
  `_connected_for_gallery`'s broad except is in the audit (83 blocks, 35
  re-raising).

### Added (artist names resolve to the catalog, 2026-09-19: #158)
- `fm9/artist_pack.py`: "sound like Devin Townsend", "give me Devin's rig",
  "install the Periphery pack", "Steve Vai tones" yield the name, which is
  resolved against the Gift of Tone catalog deterministically: every word
  of the phrase must be a whole word of an entry's artists (a full name, a
  first name alone when one artist carries it, a surname, a band name); a
  phrase that is an artist's full name beats entries that merely contain
  its words; two or more candidates is one question naming them; none is
  `absent` with the line "There is no official Gift of Tone pack for X;
  building a tone in that style from what I know, which is my
  interpretation, not their preset."
- `POST /api/artist-pack {query}` answers resolved (the entry plus a
  confirmation naming the pack and year), ambiguous (candidates and the
  question) or absent (the line), over the entries this unit can take, and
  fetches nothing. The command bar consults it before anything else for an
  artist-shaped sentence: a resolved pack is shown as an offer with a
  FETCH button and nothing is downloaded until the player clicks it (then
  the verified fetch and the per-slot installs, each a click); ambiguous
  asks in the chat; absent shows the line and sends the sentence on to
  the planner.
- Rule 23 in `config/tone_rules.md`: an artist name without their official
  pack is the planner's interpretation; the summary and preset name say
  "in the style of" and never "X's pack" or "X's preset".

### Added (Gift of Tone gallery: device gate and verified fetch, 2026-09-19: #156, #157)
- `fm9/gallery.py` on top of the J1 catalog. Device gate (#156):
  `entries_for` keeps the entries whose device matrix lists the connected
  device (the adapter kind `fm9` is the catalog's "FM9"; "All devices"
  counts), so an Axe-Fx III-only pack is not shown on an FM9;
  `firmware_gate` compares the unit's own firmware label with the entry's
  minimum for that device and answers one line when too old, when the
  unit's label cannot be read, or when the pack has no version for the
  device; with no device the catalog still browses and one line says
  installs need the unit. Fetch (#157): `fetch_entry` downloads from the
  catalog's fractalaudio.com URL only (any other host is refused), hashes
  the bytes and compares with the catalogued sha256 before anything is
  opened, caches a match under `TONECOMMAND_CACHE_DIR` or
  `~/.tonecommand/cache/gift-of-tone/<sha256>.zip` (re-hashed on every
  read), and answers a fetch failure or a hash mismatch with one line and
  nothing installed; `unpack` matches zip members to the catalog's
  contents by exact path and names anything else as unexpected, never
  handing it on.
- Routes: `GET /api/gift-of-tone` (device, firmware, the filtered entries
  with their minimum firmware, how many were hidden, the no-device note)
  and `POST /api/gift-of-tone/fetch {id}` (the gates, then fetch, verify,
  unpack, and the catalog-listed presets, cabs and .fasBundle members into
  the install cache in the `/api/acquire` shape, plus `sha256`, `source`
  cached or fetched, `verified`, `unexpected`; `.blk` effect blocks are
  reported as not installable yet). `/api/acquire` now takes the verified
  catalog path when the artist is catalogued and falls back to the page
  scrape otherwise. Installs still go through `/api/install` and
  `/api/install-cab` behind their whitelists; nothing here touches the unit.
- Tests never touch the network: `tests/conftest.py` replaces the
  gallery's downloader with one that fails loudly and points the cache at
  tmp_path (a test that faked only `acquire._download` had pulled a real
  zip once the catalog path existed).

### Fixed (user-cab installs from bundles, 2026-09-19: #43)
- Installing a Gift of Tone bundle whose map files its cabs under
  `Bank="2"` (the Steve Lukather pack) refused to write, so the preset
  landed with its cab missing. Three things were wrong, all found on
  hardware. The write layout: FM9-Edit's own write of a cab, captured with
  MIDI Monitor, puts the slot's low septet first with a 0x10 flag in the
  high byte (`0A 14 00 10` for U1.0523) and masks every fifth body byte to
  0x0F; `cabfile.retarget` sent the index bytes the other way round and
  now reproduces the ten captured frames byte for byte
  (`tests/test_cab_bank2_capture.py`, body-redacted fixture in
  `tests/fixtures/`). The address: the FM9 has one flat user-cab list
  (U1.0001 to U1.1024, 0-based on the wire) and a Bundle-Map's Bank is the
  Cab block's bank id (2 = USER), Number the slot itself, the same number
  the file head and the preset's CABINET_TYPE carry; the `(bank-1)*512`
  arithmetic is gone and any bank other than 2 is refused by name. The
  proof: the body read (fn 0x19) hangs firmware 12.x and stays off, but
  fn 0x01 sub 0x4B, which the editor sends after its own write, returns
  a slot's name at once (`FM9.read_user_cab_name`; ten slots read on the
  unit, `<EMPTY>` for empty ones), so an install is verified by the unit.
- `FM9.install_user_cab_slot(raw, slot, expect_name)` is the one path:
  whitelist by slot (`TONECOMMAND_CAB_SLOTS`, 0-1023; the refusal names
  what the slot holds now), the captured frames sent one at a time after
  the unit's fn 0x64 ack, stop on a missing ack, name read before and
  after; `verified` is True when a cab is there and, if a name was
  expected (a bundle map's), it matches. `install_user_cab_at(bank,
  number)` is the Bundle-Map adapter onto it. No install consults the fn
  0x19 guard any more; the guard stays on `read_user_cab_addr`.
  `POST /api/install-cab` takes `slot` or the map's `bank`/`number` plus
  the expected `name`, answers `ok` (a cab is there), `verified` (the
  name matches), `slot`, `editor` (U1.nnnn), `name_before`, `name_after`;
  403 outside the whitelist, 422 for a bank the FM9 cannot write. The
  simulator acks cab frames, decodes the captured head and answers the
  name read with a body-derived name.
- Verified on the FM9 (firmware 12.x, 2026-09-19): ToneCommand wrote the
  Lukather pack's two cabs to U1.0523 and U1.0524, the unit's name read
  returned both names, and in an A/B in FM9-Edit's Cab block the
  ToneCommand-written IR sounded the same as the editor's own import of
  the same file. Known: FM9-Edit shows a cached cab list; use its refresh
  button to see slots written by anything else.
- Still open, filed separately: a pack's preset points at fixed slots
  (the Lukather preset wants U1.0012 and U1.0013, which hold the player's
  own cabs); moving a pack's cabs to free slots and repointing the preset
  belongs with the pack gallery (#164, before #155).

### Added (NAM captures and Fractal sources, 2026-09-19: #144, #145, #161, #154)
- `fm9/nam.py` reads a `.nam` capture file (stdlib json only) into a
  CaptureRecord: architecture and config summary, the metadata the file
  carries, `needs_cab` from gear_type (amp, pedal, pedal_amp, preamp and a
  missing gear_type need a cab; amp_cab, amp_pedal_cab, studio are full rig),
  `scene_role` from tone_type (clean; overdrive, crunch, fuzz to rhythm;
  hi_gain to lead). Anything absent is "not on file", never inferred;
  malformed input is refused with one line.
- Rule 22 in `config/tone_rules.md`: capture or model, the wording decides,
  never a setting. `fm9/capture_intent.py` is the deterministic half (whole
  phrase, word boundary, last phrase wins) and every plan now carries
  `amp_source` with an honest line; until the FM9 has a NAM block every build
  is the model and the line says so when a capture was asked for.
- `catalog/gift_of_tone.json`: all 34 Gift of Tone entries with artists,
  year, number, kind, Fractal's description, the device matrix as the page
  states it, the zip URL with sha256 and size, and the contents (presets,
  cabs, .blk effect blocks, every .fasBundle's bundle map with cab bank and
  number). Built by `tools/gift_of_tone_catalog.py`; published by the site at
  `/gift-of-tone.json`; read site-first by `fm9/gift_of_tone.py`. Nothing
  mirrored.
- The Fractal sources terms and fetch policy (kb/SITE.md): Axe-Change is never
  fetched by the tool (its terms grant no download licence); Gift of Tone is
  pinned URLs fetched at click time.


### Changed (verification procedure, review of #134: 2026-09-19)
- A SAFETY CHECK MUST NOT BE THE THING IT CHECKS FOR.
  `tools/verify_headrush.py` probed AC4 by calling `deleteRig` and by writing
  `ModuleType` ordinal 20, the ordinal that killed the engine, to a hardcoded
  slot that is occupied on a real rig. Both were safe only if the interlock
  worked, which is the thing under test. The probe is split: the dangerous
  names and ordinal 20 are asserted as data with nothing called, and the
  transport behaviour is checked with a method name no device implements and
  with ordinal 254, which finding 1 measured as harmless, in a slot measured
  empty on the loaded rig.
- AC7 IS NOW TRUE. The report claimed print-time redaction while the host was
  printed unredacted and edited out of the committed transcript afterwards.
  `Report.record` runs every line through `redact()`, seeded before the first
  line of output, so a host or rig name arriving inside an exception message
  cannot reach the transcript either.
- THE RESTORE RUNS EVEN WHEN A CHECK EXPLODES. `verify()` was called bare, so
  any exception it did not convert to a FAILED row skipped the reload and left
  the unit holding the run's writes, possibly chain edits. It is wrapped, the
  reload is in a `finally`, and a restore that itself fails is reported as a
  failed check naming what to do rather than passing silently.
- REFUSAL CHECKS REQUIRE THE RIGHT EXCEPTION. Two checks treated any
  `Exception` as a pass, so a transport error or a `TypeError` greened AC4 and
  AC5. `Report.expect_raise` fails on an unexpected type and says which
  arrived.
- RIG READ-BACK POLLS INSTEAD OF SLEEPING. Measured over 16 loads, the swap
  lands 159..679 ms after the call with no predictor: not the rig, and not
  whether it was just loaded. A fixed settle either flakes at the tail or pays
  the worst case every time, so `wait_for_rig` polls and returns as soon as the
  engine has swapped.
- The topology check requires a real transition rather than always writing
  routing 1, the scene restore snapshots the scene engaged at entry rather than
  assuming the first scene-mode switch, `dirty` is reported rather than
  identity-checked against `False`, and detail strings use `.get` so a missing
  key cannot raise inside a check.

### Added
- `tests/test_verify_headrush.py`: the procedure's own guards, which had none.
  Covers print-time redaction, the typed refusal checks, the opener counter,
  a failing check not ending the run, the `##HRB` interlock refusing a real
  rig, and the restore running when `verify` raises. Two fail if the
  corresponding fix above is reverted.

### Found on hardware (review of #136)
- A RIG IS NOT LOADED WHEN `loadedName` SAYS IT IS. The name flips 185..332 ms
  after `loadRig` while the chain is still the PREVIOUS rig's, and the chain
  keeps being rebuilt for up to a second after that. A write issued in that
  window races the tail of the load and loses: the unit installs the rig's own
  stored value over it and the read-back reports a mismatch that is not the
  writer's fault. This is what the "unexplained" topology transient was.
  `Routing` itself is fast, read back in 17..38 ms over 14 writes, so a slow
  write was never the explanation.
- `wait_for_rig` waits for the name, for the chain to differ from the shape
  captured BEFORE the load, and for that shape to hold across three reads.
  Quiescence alone was the first fix and it was wrong: the previous rig's
  chain is quiet too, and was measured quiet for about a second, so waiting
  for stillness could succeed on the old chain and return just as early. A
  chain that legitimately never differs, from reloading a rig or loading one
  with the same chain, waits out a 2.5 s ceiling instead of failing. Three
  consecutive full runs pass, where the previous build failed two of five.
- The same race applies to anything that loads a rig and then writes,
  `select_preset` included. Reported on #134; the adapter is @monzta1's.

### Changed (review of #136)
- A REFUSAL MESSAGE REPORTED THE COUNT FROM BEFORE THE CALL. `expect_raise`
  took `detail_ok` as a formatted string, which is evaluated before the call
  it describes, so "refused before transport" printed the same opener count
  whether or not anything went out. It takes a callable now. This is the same
  uninformative-message class the topology check was just fixed for, and it
  was reintroduced by an argument's evaluation order.
- AN UNREADABLE UNIT COUNTED AS A CLEAN ONE. The restore row tested
  `not dirty_after`, and a failed read returns `None`. Only an explicit false
  reading counts now, and `discard_edits` raises when the rig does not come
  back rather than returning quietly.
- `wait_for_rig` sleeps on the error path. It used to `continue` with no
  delay, turning a transport blip into a tight spin against a unit that is
  already struggling.
- `Ctrl-C` is no longer swallowed. `except BaseException` caught
  `KeyboardInterrupt` and returned 1, reporting an interrupted run as an
  ordinary failing one; it restores and re-raises.
- The redactor is seeded with rig IDS as well as names, which AC7 also
  promises are absent.
- The "only transport" check claimed more than an assertion can show from
  inside the run. It asserts the adapter holds the wrapped client and says so;
  the single-call-site property is documented, not dressed up as a
  measurement.

### Verified on hardware
- #135's `select_preset` fix passes against the Core at 5.1.0.2a63755. The
  full pass is 36 checks, 0 failed, three runs in a row.

## 1.3.1 (2026-09-19)

### Added (device picker, 2026-09-19: #139, the follow-up #94 left)
- With more than one device reachable, the header shows a DEVICE pill (amber
  CHOOSE DEVICE until a choice is made) with a popover listing every reachable
  device; choosing one goes through `/api/device/select` and a refusal (GIG
  LOCK, a reviewed plan pending, a kind not here) is shown in the server's own
  words. `/api/state` carries a `device` block on every answer. The link pill
  follows the active device by a fixed short-name map, so the FM9 still reads
  exactly `FM9 · LINKED`, and with one device nothing is rendered at all. A
  build refused with `ambiguous_device` opens the picker and says "choose a
  device first". A stale poll can never revert a fresh selection (generation
  guard).

### Added (the IRCommand seam, 2026-09-19: #137, #138)
- #137: a library candidate that is already on the FM9 (its file linked to a
  user cab slot) is `on_rig` and comes first in the listening set, in
  IRCommand's own order inside each group, and the cab panel gives it
  AUDITION ON RIG (the real amp path) with PREVIEW kept beside it; the list
  renders under ON YOUR RIG and IN YOUR LIBRARY (load it with Cab-Lab first).
  With a measured Current, each measured candidate carries per-feature deltas
  (low, mid, presence, fizz, brightness, via IRCommand's `/ir/measured`
  features) and short words for the moves big enough to hear ("tighter low,
  more presence"). A gear-anchored Current still gets no numbers.
- #138: the scene's role (`tone_review.infer_role` on the current scene name,
  never on a whole-rig build) and the guitar's tuning (`fm9/tuning.py`, a
  deterministic parser over the player's words in IRCommand's vocabulary)
  travel to `/ir/recommend` as `role=` and `tuning=`, only when known;
  `cab_selection.hints` reports what IRCommand applied, and the cab note reads
  "Ranked for a lead scene in drop C", or says the library build ignores the
  hints when it did not echo them.

### Fixed
- Two page classes had no CSS rule (`cabgroup` from #137 and `cbuildthis` from
  the advisory lane); `tests/test_ui_warning.py` caught them in CI. Both are
  styled now.
- Cab rows: the reasons and measured moves under a candidate's name were
  ellipsized with the name and the separator showed as a literal `&middot;`;
  they now wrap on their own line with a real middle dot.

### Fixed (HeadRush adapter, 2026-09-18: #135, from the #126 hardware pass)
- `HeadrushAdapter.select_preset()` sent the rig NAME to `loadRig`; the Core
  answers 504 and loads nothing (found by @bschmalz81401's pass, PR #134). It
  now resolves a name to the rig id through the parallel `AllRigNames` /
  `AllRigIds` lists (an id is accepted directly), calls `loadRig(id, "")`,
  and waits the settle before reading `PresetName` back, since `loadRig`
  returns before the engine swaps. The simulator gains `loadRig` on
  `/Evil/API/Rigs`, loading by id and answering 504 for a name, so the path
  is executed under test: it was the one adapter method nothing had ever run.
- `SceneActive{n}` is now a measured LATCH (engaging a second scene leaves its
  flag True and clears the first's); the adapter's comments say so, and
  `LastScene` stays the success signal because it names the scene.

### Added (HeadRush adapter hardware verification, 2026-09-18: #126, #33)
- `tools/verify_headrush.py`: the dedicated hardware verification procedure for
  #126. Runs the #125 adapter against a real Core, one check per acceptance
  criterion, each tagged with the criterion it serves. Refuses to start unless
  the loaded rig is a `##HRB` test preset, restores what it touches, and ends by
  reloading the rig by id so the edit buffer is discarded without storing.
  Exit status is 0 when every check passes and 1 when any fails, so it can gate.
- REFUSED BEFORE TRANSPORT IS CHECKED AS SUCH (AC4). Catching an exception
  proves the adapter raised; it does not prove nothing reached the unit, which
  is what the criterion asks. The client's opener is wrapped in a counter and
  the check asserts the count is unchanged across the refused call, for both a
  non-allowlisted `object-method` and `ModuleType` ordinal 20.
- `docs/HEADRUSH-VERIFICATION-126.md`: the scrubbed report (AC7). Redaction
  happens in the script at the point of printing, so the transcript is committed
  verbatim rather than edited into shape; no rig name, rig id, setlist or preset
  content appears in either file.
- THE FIVE-STEP PASS FROM #33 is carried by the same procedure, tagged `#33`
  rather than `AC` so the ticket's criteria stay separable. All five pass, and
  both questions left open in that comment now have answers.
- `SceneActive{n}` IS A LATCH, NOT A PULSE. Measured across a transition,
  because a flag read back immediately after its own write is equally
  consistent with both: engaging a second scene leaves the second's flag True
  and clears the first's. `LastScene` remains the better success signal, so
  `set_scene` requiring the flag is now an option rather than a defect.
- ORDINAL 4 IS REPORTED NOT PLACED, AND NOT FALSELY OK. The device accepts the
  write and silently reverts to 0; the adapter's 0.5 s settle catches it and
  returns `ok=False`. An immediate read-back would have seen `4` and lied.

### Known issues
- (Fixed in this release by #135, see "Fixed (HeadRush adapter)" above; kept as
  the #126 pass reported it.) `HeadrushAdapter.select_preset()` DOES NOT WORK AGAINST HARDWARE. It passes
  the rig name as `loadRig`'s first argument; the unit answers `504 Gateway
  Timeout` and loads nothing, where the rig id returns `True` and loads. The
  method has no test, and `devices/headrush/sim.py` does not implement
  `loadRig`, so it reached main and 1.3.0 having never been executed against
  anything. It also reads `PresetName` back with no settle, though `loadRig`
  returns before the engine swaps. Evidence in
  `docs/HEADRUSH-VERIFICATION-126.md`; the fix is #125's, reported separately.
### Added (advisory lane, 2026-09-18: #68, #69, #70, #6)
- ADVISORY MODE, THE DETERMINISTIC HALF. `fm9/advisory.py` reads
  edit-buffer captures and answers three questions from numbers, never
  with an action (it imports no executor; its routes have no `actions`
  key):
  - compare (#68): every difference between two captures, exhaustively
    (blocks on one side only, engagement, active channel, amp model, cab,
    typed families, every parameter on each capture's active channel, raw
    for uncalibrated ones), narrated in plain lines ("B has more amp gain
    (7.2 vs 5.5)", "B runs the 4x12 1960B V30 cab, a brighter cab").
  - close the gap (#69): the moves that take A toward B as advice
    (block, parameter, from, to, why) plus one sentence the planner can
    act on; BUILD THIS in the chat sends that sentence to /api/plan like
    any typed request, through validation and confirm-before-send.
  - diagnose (#70): muddy, boomy, thin, harsh, fizzy, dark, buried. A
    curated table of checks against the capture (amp bass/mid/treble/
    presence/gain/depth, low and high cut, drive engaged, delay and reverb
    mix, EQ engaged, cab name voice), each answering likely (with the
    value read and the tone_rules.md rule it rests on), cleared, or not
    readable; at most three directions to try; an unknown symptom is
    refused with the list.
- Routes `POST /api/advise/compare`, `/gap`, `/diagnose`. Sources are
  `snapshot:a|b|undo`, `scene:N` or a scene name (the tool stands in the
  scene to capture it and puts the original scene back; nothing else is
  written) and `design:NAME` (a saved design applied to the current
  capture, read-only). Comparing two stored presets means comparing their
  snapshots: selecting another preset would discard the edit buffer,
  which is the loss undo exists to prevent.
- The chat routes three question shapes deterministically before the
  model sees them ("difference between X and Y", "get X closer to Y",
  "why does my <scene> sound <symptom>"), prepends the measured findings
  under a fixed heading, and shows them as a card under the reply, so the
  prose rests on numbers. Ordinary sentences with those words go to the
  model unchanged; objects must be a scene of the loaded preset, a
  snapshot slot or a saved design, or the question is not routed.
- CAB PAIRING IN THE PLANNER REFERENCE (#6, closing). Every amp line
  carries its guide pairing ("pairs with Fender 4x10 Jensens; DynaCab
  4x10 Bassguy RI -> factory bank 1 ordinal 194 4x10 Bassguy 57 B") where
  the sidecar has one, with the factory target only when the DynaCab name
  resolves in the catalog (24 of 47 do; none are guessed). The reference
  now says that set_cab is a plannable, read-back-verified write. Growth
  measured: 741 to 743 lines.
- The broad-except audit now covers 82 blocks (34 re-raise, 48 unreachable).

## 1.3.0 (2026-09-18)

### Added (HeadRush lane, 2026-09-18: #123, #124, #125, #94)
- ONE DEVICE-OWNED POSITION (#123). `ChainEditing.place_block(position,
  effect_id)`: the FM9 passes a `GridPos(row_1based, col_1based)` (or a
  plain pair) and sends exactly the select-cell and set-cell frames it always
  sent, asserted against the protocol builders; a rig device passes its slot
  number and invents no row. Every caller converted; `conformance()` rejects
  the old row/col shape.
- A SELECTED DEVICE CONTEXT (#124). `server.DeviceContext(kind, registry,
  adapter)` pairs exactly one adapter with its own catalog; `get_fm9()` hands
  out the selected adapter, gated as before, and the module-level `reg`
  resolves on every access to the selected context's registry, so the
  seventy-odd validation, planning and snapshot lookups read the right
  catalog without a parameter threaded through each. The default is the FM9
  with its lazy connect, unchanged. Tests inject a device through
  `server.use_device(...)`, never by patching the FM9 class.
- WHICH DEVICE (#94). `available_devices()` lists what this process can
  reach (the FM9 always; a HeadRush when `TONECOMMAND_HEADRUSH_HOST` or
  `TONECOMMAND_HEADRUSH_SIM=1` is set); `GET /api/device` reports it;
  `POST /api/device/select {kind}` switches the context (423 under GIG
  LOCK, 409 with a reviewed plan pending, 404 for a kind not here). With
  more than one device and no choice, `/api/plan` and `/api/plan/stream`
  answer 409 naming the choices instead of acting on a guess; with one
  device nothing changes.
- THE HEADRUSH ADAPTER (#125). `devices/headrush/adapter.py` implements
  the contract over the committed client, registry and topology table:
  ten routings by index, fourteen slots by number, tri-state scenes by slot
  name, bypass through the block's own `On`. Capabilities are the measured
  ones and each False states why (no store, no modifiers, no installs, no
  rename measured; chain state unreadable until a rig is loaded).
  `conformance()` is empty. Every property write goes through one path that
  reads the value back after a 0.5 s settle (finding 1: ordinal 4 is
  acknowledged and gone by 0.39 s), and a placement additionally requires
  the module's object to answer (ordinal 254 sticks with no object).
  `object-method` is deny-by-default: only `/Evil/API/Rigs loadRig` is
  reachable; ModuleType 20 (measured engine death) and 254 are refused
  before transport. `evidence()` names the unit (HeadRush Core,
  5.1.0.2a63755, 2026-09-15) and the unverified models (Prime, Flex
  Prime). Continuous parameters are written on the 0..1 wire only:
  display conversion is refused with the registry's reason, because the
  curve is an opaque taper id the device never explains (finding 3).
- The broad-except audit now covers 79 blocks (34 re-raise, 45 unreachable).

### Added (FM9 lane tranche, 2026-09-18: #43, #82, #83, #84, #96, #97, #98)
- AUDITION BEFORE COMMIT (#83). `POST /api/cab/audition {bank, ordinal}`
  points the CABINET block at a cab that is already on the unit, in the edit
  buffer, through the same two discrete writes a plan's `set_cab` makes
  (`server._select_cab`, now shared by both); `POST /api/cab/audition/end`
  puts the pre-audition cab back; `GET /api/cab/audition` reports the
  session. Start is transactional: a write or read-back that does not land
  restores the original, clears the session and answers 502. A restore that
  does not land keeps the session OPEN with `last_error` so it can be
  retried, rather than leaving the unit quietly pointed at the audition cab.
  Nothing here stores and nothing touches the user-cab wire; the simulator
  tests assert both from the sent frames. Proven live on the FM9: preset 18
  read back `1x12 AC-20 DLX MIX`, the audition read back `4x12 1960B V30
  (RW)`, the end read back the original.
- NEVER ONE CAB (#82). `server.factory_cab_shortlist()` and
  `GET /api/cab/shortlist?q=` search the whole factory catalog and return
  meaningfully different takes: distinct cabinets first (mic and take
  stripped, split at the family word so `2x12o V30 107 Room_L` and `Room_R`
  are one cabinet), then further mics of those. A plan whose `set_cab` got
  nothing from the IR library to be compared against now carries that
  shortlist as its listening set, the plan's own pick first and marked, so
  no cab is handed out alone; fewer than two matches says so in `why`.
- The review's cab panel gives every on-rig row an AUDITION ON RIG button
  (HEARING NOW on the one playing) and a RESTORE ORIGINAL control that names
  the cab you had. USE THIS is still the only way a cab enters the build.
- SCRATCH SLOT CLEANUP (#84). An audition never writes a slot, so there are
  no leftovers by construction; ending it, starting a new plan, or the
  device handle being dropped restores the original first. `config/README.md`
  documents the highest `TONECOMMAND_CAB_SLOTS` entry as the scratch slot for
  Cab-Lab installs and the lower one(s) as the commit target.
- REQUEST TENSION, SECOND PASS (#98). `fm9/request_tension.py` gains a
  synonym layer (punchy/percussive/chunky for tight, smooth/mellow/woolly/
  muffled for warm, washy/cavernous for wet, bedroom/whisper for quiet,
  retro/classic for vintage, brutal/chuggy for modern high-gain, and a new
  bright/sparkly/glassy versus dim/dull/no-top-end pair leaning bright per
  rule 9). Matching is word-boundary, longest phrase first, one finding per
  pair, and every term belongs to exactly one pair (checked at import and by
  test; design review caught `muffled` and `woolly` listed on two pairs).
  Plan results carry `request_tensions` and the plan stage shows a REQUEST
  TENSION card above the summary, built from that data rather than from
  whether the model repeated it.
- RULES 18, 19 AND 20 (#96, #97) in `fm9/tone_review.py`, all warnings for
  the reason rule 17 is one: no professional reference data measures them.
  Rule 18: a voiced clean with no modulation engaged when the request asks
  for a big/80s/lush/shimmer clean (`review()` now takes the request text).
  Rule 19: a rhythm or lead with amp MID at or below 2 on the 0-10 scale
  reads as scooped/thin (`Scene.amp_mid` from `DISTORT_MID`). Rule 20: a
  utility block (VOLUME, MIXER, LOOPER, sends, IR capture, ...) the plan
  engages and then sets nothing on, binds no pedal to and picks no channel
  for is clutter. `FAMILY_CLASS` gains the `utility` class.

### Security (#43)
- THE fn 0x19 USER-CAB READ IS OFF BY DEFAULT. Measured 2026-09-05 on
  firmware 12.x: one read disconnected the FM9's MIDI and the unit needed a
  power cycle. That read was the safety step of every user-cab install
  (probe the address before writing), so every install inherited the hang.
  `fm9.device.cab_read_guard()` now refuses as the FIRST statement of both
  `read_user_cab_addr` and `install_user_cab_at`, before parse, whitelist or
  any candidate address is tried, so no frame can be built without
  `TONECOMMAND_ALLOW_CAB_READ=1`. The message names the hang, the recovery,
  the supported route (48 kHz WAV through the free Cab-Lab 4 into a user
  slot, then `set_cab`) and the issue; `/api/install-cab` answers it as 409.
  Bank 2+ addressing itself stays open on #43: it cannot be probed without
  the read that hangs the unit.
- The broad-except audit now covers 78 blocks (34 re-raise, 44 unreachable):
  the six new ones wrap `get_param_wire`/`set_param_ordinal` on
  `DeviceAdapter`, behind no gate, and `request_tension`, which has no
  device handle.

### Verified (HeadRush scene model, 2026-09-18)
- THE SIMULATOR'S SCENE MAPPING IS CORRECT. `devices/headrush/sim.py` models
  scene slots as `{0: no_change, 1: on, 2: off}`; that constant is on `main`,
  phases 4 and 5 get written against it, and it had never met a unit. An
  inverted mapping would have inverted every scene an adapter wrote, with the
  simulator agreeing all the way down because both share the constant.
- `Scene{n}_{m}_Mode` publishes no option names, so this is not readable from
  the schema. 1 and 2 were measured by engaging four scenes and comparing every
  Mode 1 or 2 slot against that block's own `On`: 38 predictions, none wrong,
  counted by script after an earlier draft reported the total wrong.
- 0 was measured in BOTH DIRECTIONS, because one is not enough. A block held ON
  through a Mode 0 scene shows 0 is not off; on its own it is equally consistent
  with 0 meaning ON and the scene writing a value the slot already held. So the
  same block was also turned OFF by hand and held OFF through the same scene,
  which moved nine other slots each time. Neither alone identifies no_change;
  together they do. The one-directional version was caught by review.
- SCENE ACTIVATION IS ON THE API: writing `SceneActive{n} = true` engages scene
  n and applies its table, provided `ModeNew{n} = 2`. An earlier version of this
  entry said activation was not available at all, which came from writing
  `SceneActive` on a blank preset where no switch was in scene mode. The
  dependency on `ModeNew` was already measured and documented in
  `bschmalz81401/HeadrushRigBuilder` on 2026-09-07, and was not consulted.
- The index is CONSISTENT: `ModeNew{n}`, `FootSwitchText{n}`, `SceneActive{n}`
  and `Scene{n}_{m}_Mode` share one n, and only `LastScene` is zero based at
  n - 1. An earlier version claimed four different numbers for one scene, with
  the footswitch index below the SceneActive index. That was wrong, and it
  rested on a property read taken WHILE a rig was loading: the labels were
  shifted by one against the settled values and `loadedName` came back empty in
  the same response. A read during a load can mix rigs, and a scene table is
  exactly the shape where that is invisible.
- The simulator models the slot data and not whether a scene is CONFIGURED.
  Slots exist on every rig including blank ones, so their presence says nothing;
  `SceneNumberOfStates{n}` and `ModeNew{n}` carry that. Recorded as a gap.
- `loadRig(<rig id>, "")` on `/Evil/API/Rigs` loads a rig and returns `True`:
  the first `object-method` call this project has made on hardware. The method
  surface returns meaningful values rather than only 200 or 504, so an
  allowlisted method can be verified by its return, which matters given how
  poorly read-back performed on the ordinal tests.

### Fixed (post-merge corrections, 2026-09-16)
- A follow-up review of the final state of #127, #128, #129 and #130, after all
  four merged, found things the first pass could not: the fix commits were
  themselves unreviewed, and several published numbers had moved.
- `describe_unreachable()` was BLANKET-CLAIMING that a 404 rules out HeadRush
  Remote. The measured table is path dependent: with Remote off,
  `object-properties` and `object-meta` answer 403 but `subtree` answers 404.
  So the claim was wrong for exactly the endpoint `client.subtree()` uses. It
  now classifies on the request URL as well as the status, and says how to
  disambiguate. The test that covered this asserted the overclaim, which is
  what kept it alive; it is replaced by one test per path shape.
- Five published strings still said the taper grid was 726 points after it
  became 990 (`CHANGELOG`, `THIRD_PARTY_NOTICES`, `config/README.md`,
  `devices/headrush/tapers.py`, and the docstring of the test that asserts 990).
  The notices one was a false statement about the committed file.
- The registry's read-only count was wrong in a comment: 893 per object comes
  from 448 unique metas among those the registry INCLUDES, not from the 491
  that counts all 161 metas and expands to 936. Different scopes rather than
  unique versus expanded of one set.
- `grid` versus format precision is 1840 of the 1880 that publish both, with 40
  diverging, not 1841 of 1881. `UsedSpace` publishes a format and no grid.
- `wire_encoding.measured_on` counted `Amp.TremDepth` among the readings that
  establish the 0..1 wire. It does not: 0 reads as 0 under either scale, so it
  discriminates nothing. Recorded as a reading that was taken and does not bear
  on the claim.
- Two registry docstrings restated findings that had already been withdrawn:
  one kept the "high pass off" interpretation the generator had dropped, and
  one said nothing in the schema tells two tapers apart, which stopped being
  true when `normalizeAlgo` was carried through as `taper_id`.
- `devices/headrush/sim.py` now shapes an error the way the REAL unit shapes
  one, MEASURED on a Core rather than reasoned about. Two earlier attempts got
  it wrong in opposite directions and nothing failed, because nothing asserted
  it: the first put the whole `SimError` text in the reason slot, so a missing
  path rendered "HTTP Error 404: 404 no object at ..."; the second used the
  bare message, which stopped the doubling and still did not match.
- What the unit sends: `reason` is the standard phrase (`Not Found`), the
  description is in a JSON body (`{"desc": ..., "reason": ..., "status": ...}`)
  with `Content-Type: application/json`, and the header object is
  `http.client.HTTPMessage`, not the `email.message.Message` an earlier fix
  used because it merely was not None. The body also still carried the doubled
  prefix the previous entry claimed to have removed.
- Tests now assert that shape, including that neither the reason nor the body
  starts with the status. A test that read the description out of
  `str(error)` was passing only because the sim was wrong, and now reads the
  body.
- `describe_unreachable()`'s 404 branch classifies on the ENDPOINT SEGMENT
  rather than a `"/subtree" in url` substring, and only makes the "this is not
  Remote" claim for `object-properties` and `object-meta`, the two endpoints it
  was measured on. `object-method` and an unreadable url now get neither claim
  and say the behaviour there was not measured.

### Added (HeadRush block and parameter registry, 2026-09-15)
- `config/headrush_registry.json` plus `tools/build_headrush_registry.py` and
  `devices/headrush/registry.py` (#122): the committed schema turned into the
  lookup a planner uses. A block by name or path, its parameters classified
  into the kinds a caller must treat differently, and the `ModuleType` ordinal
  that selects it into a chain slot. Generated, deterministic, no hardware.
- CONTINUOUS VALUES ARE NORMALISED 0..1 ON THE WIRE while the published
  `minimum`, `maximum` and `format` describe the scale the unit SHOWS.
  Measured on a Core by writing a value and reading the unit's screen:
  `Amp.Bass` at wire 0.75 reads 75 %, `Amp.PostGain` at 0.5 reads 0.0 dB on a
  -12..12 range. The device accepts a write of either 0.75 or 75 without
  clamping, so nothing on the API discriminates and only the screen settles it.
- No normalised-to-display conversion is offered, because the device NAMES each
  curve without describing it. `x-options.normalizeAlgo` is an opaque integer,
  carried as `taper_id`; the formula behind it is unpublished. Measured off the
  unit's screen: `Amp.Bass` and `Amp.PostGain` carry no id and are linear,
  while `Amp.TremSpeed` carries id 5 and is quadratic, reading 1.48 Hz at wire
  0.25 and 5.19 Hz at wire 0.5 on a published 0.25..20 range where linear would
  give 5.19 and 10.125. Solving for the exponent at each point gives 2.0023 and
  1.9993, so that is two independent readings rather than one fitted point.
  `Parameter.to_display()` exists only to refuse.
- Absent is NOT treated as meaning identity, though it fits all four readings:
  four parameters on one block is not a decoding, and ids 6, 8 and 10 have
  never been read. Unit does not predict taper either, so no per-unit shortcut
  is available: `C2_Bass_Chorus.Depth` is a percentage carrying id 6. Left open
  on #126, which needs no human at the hardware because the unit's own web
  editor renders these values.
- Every field the device publishes travels verbatim in each parameter's
  `published` map, including ones nothing here interprets, with `read_only` and
  the device's own `grid` step alongside. A test proves that set complete
  against the schema rather than against a list that could fall out of step.
  This came out of independent review: the first draft kept only the fields it
  had a use for, so `normalizeAlgo` never reached the registry and the registry
  then told callers the taper was unpublished while the schema it was generated
  from was publishing one. 893 read-only properties are now flagged, including
  `/Evil/Gui.DeviceName`, which a planner could otherwise have offered to
  rewrite.
- `RegistryCorrupt` is separate from `SchemaDrift`: a block naming a parameter
  set the file does not hold is the file disagreeing with itself, which wants a
  restore, not the regenerate-and-read-the-diff that drift wants.
- Three roster entries have a `ModuleType` ordinal and no object: `ReValver
  Amp 2`, `Neural Amp Modeler 2` and `C-Verb 2`. That is the unit's one
  Capture and one C-Verb per rig rule showing up in its own data, so they are
  recorded with their ordinals rather than dropped to make the join come out
  even. Whether writing one of those ordinals is refused, ignored or accepted
  is a hardware question and is left open on #126.
- Block CATEGORY is absent rather than inferred: the device has the vocabulary
  and answers per block by method, and that answer is not in the schema. No
  FM9 effect or parameter equivalence is recorded either, for the reason
  `tools/build_headrush_amp_models.py` sets out at length.
- A property whose name ends in `2` is NOT read as the B half of a doubled
  block. On `Amp` that is what `Bass2` is, and generalising it would be wrong:
  `Chain.CanDouble12` is slot twelve and `Vocal_Harmony` carries `On2`, `On3`
  and `On4` for harmony voices. No rule can tell those apart, so none is
  applied.
- `load()` refuses to serve answers derived from a schema the repo no longer
  holds, and names which of the two causes it is: a firmware bump wants both
  files regenerated and the diff read, while an unchanged firmware with a
  changed hash means the schema was hand edited, which #117 says not to do.
- Objects share parameter sets the way they share metas upstream, 302 objects
  to 153 distinct sets, stored once and referenced by hash. Without it the
  derived file was 1.7 MB against the 1.0 MB schema it comes from. The dedup
  is lossless by check: a hash already holding a different set is refused.

### Fixed (secret scanner, 2026-09-14)
- `test_secret_key_never_hardcoded` matches the SHAPE of a TONE3000 key rather
  than its prefix. Matching `t3k_cs_` flagged four places that hold no secret:
  its own search literal, the generator's docstring, and the two prefix checks
  that exist to reject the wrong key type. The guard was therefore red from the
  day it landed, and a secret scanner that is always red is one nobody reads on
  the day it finds something real (#112). A regex for the prefix plus a body of
  at least 20 characters clears all four and still catches a planted key, which
  is proven both ways by two new tests rather than assumed.

### Added (HeadRush simulator and topology model, 2026-09-15)
- `devices/headrush/topology.py`: the ten signal-path templates as a model. A
  HeadRush rig is one of three genuinely different shapes, straight,
  split/rejoin, or two independent paths, and #121 says not to flatten them
  into an FM9 grid. `role()` says which parallel branch a slot is on;
  `path_of()` says which independent PATH, which is a different question and
  the one a dual answers, because every dual reports COMMON on all fourteen.
- `config/headrush_topologies.json` plus `tools/build_headrush_topologies.py`,
  marked `api_readable: false` and `provenance: "vendor editor bundle"`. The
  unit publishes the ten NAMES on `Chain.Routing` and nothing about their
  shapes: writing each in turn leaves every per-slot property byte-identical
  (#109). Read out of the vendor's own editor, which is the best available
  source and is still not the API, and both fields travel onto every
  `Topology` so nothing downstream can present them as a device read.
- Dual-path partitions are measured off the editor's slot geometry rather than
  parsed out of routing names, because the names do not always carry one:
  `Dual Path 4-10` states a partition and `Dual Straight Path` states nothing.
  Each records which axis carried the split, and a name that disagrees with the
  geometry makes the generator refuse rather than pick.
- `devices/headrush/sim.py`: a HeadRush that exists only in this process, built
  from the committed schema rather than a handwritten device model, so phases 4
  and 5 can be reviewed by someone who owns no HeadRush. It implements the
  injected opener from #116, so the real client code runs against it, and it
  raises `urllib.error.HTTPError` at that boundary because that is what the
  Opener contract promises callers and what production throws.
- Scenes live on the device's own `/Evil/Engine/FootSwitch` properties,
  `Scene{n}_{m}_Effect` and `Scene{n}_{m}_Mode`, not in a side table. The mode
  integers carry no names on the device; which is which was measured on a Core
  and cross-read from its bundle, and is cited rather than inferred.
- It refuses rather than smooths: an unknown path is a 404 and not a blank
  object, `object-method` is a 501 recorded in `undecoded` because no method's
  behaviour is established and #125 gates them behind an allowlist, and
  `load_rig` says out loud that stored rig CONTENTS are not modelled.

### Fixed (HeadRush unreachable diagnosis, 2026-09-15)
- `describe_unreachable()` gains a 403 branch and its 404 branch stops blaming
  the wrong thing. MEASURED by toggling HeadRush Remote on a Core with no
  reboot (#126): with Remote off, every `object-properties` and `object-meta`
  path answers **403** and the unit says why in the body, "DataModel: Web
  access temporarily disabled"; turning it back on restores 200 immediately.
- A **404** is therefore the case where Remote is demonstrably NOT the problem.
  It means this firmware has no such path, or the engine is not running: after
  the crash in the findings report, every `/api/v1` object path returned 404
  while the unit still served its editor page on `/`.
- The first version of this branch had it backwards, telling anyone who saw a
  404 to go check HeadRush Remote. It was built on the editor's own dialog,
  which names Remote for every connection failure because it is generic advice
  rather than a diagnosis. It was labelled as inferred, which was honest, and
  it still pointed operators at the one thing that was fine. One toggle settled
  it, and the toggle should have come before the advice.
- Other status codes keep their wording; the existing 504 case is unchanged.

### Added (HeadRush hardware findings, 2026-09-15)
- `docs/HEADRUSH-HARDWARE-FINDINGS.md`: partial evidence for #126, which cannot
  be completed until #125 exists, recorded now because one item is a safety
  finding affecting work in flight.
- A WRITE OF `ModuleType` ORDINAL 20 WAS FOLLOWED BY ENGINE DEATH on one Core at
  one firmware. `Neural Amp Modeler 2` is in the device's own roster, in the
  published range 0..277, and has no object behind it. The write was accepted
  and echoed back, and `/api/v1` was gone at the next two-second poll; the unit
  then reloaded itself and asked whether to load the last preset. Bounded
  deliberately: n=1 for the isolated run, slot 3 on an empty rig, and the
  timing is a poll bin rather than a measured latency. An earlier mixed
  sequence that also ended with the API gone is written out rather than counted
  as a second reproduction, since three writes cannot isolate one.
- Read-back verification does NOT detect it. The write was acknowledged, the
  read-back agreed, and the engine died after. That is the part that generalises
  and it constrains any verified-write built on read-and-compare.
- ALL THREE unbacked ordinals have now been tested, with their backed siblings
  as controls, and they do three different things. 4 is acknowledged and then
  silently reverted to 0 by the device within ~0.4s. 20 takes the unit down.
  254 sticks and does not crash, but `/Evil/Engine/Patch/C-Verb_2` stays absent
  while it is placed, so the slot holds a block with no object to address. The
  three backed siblings (3, 19, 253) all simply stick.
- SO "UNBACKED" DOES NOT PREDICT A CRASH. The earlier recommendation to refuse
  all three rested on a class generalised from the one member that had been
  tried, and the CLASS was wrong; the recommendation itself was conservative,
  refusing 4 and 254 as a judgement pending measurement rather than claiming
  they crashed. Revised now that they are measured: refuse 20 on the evidence;
  no refusal is required for 4, which the device rejects itself, though a
  prompt read-back is not enough to see that; refuse 254 as well, for the much
  weaker reason that it occupies a slot with no object to address.
- Verification needs three different checks, and read-back of the written value
  is only one of them. 20: no read of the ModuleType catches it, prompt or
  delayed, because the value is not what went wrong. 4: a prompt read-back
  reports success for a write the device discards by t+0.39s, but a DELAYED
  re-read sees 0 and is correct. 254: read-back is correct and stays correct,
  so this is not a read-back failure at all; what detects it is object presence
  (`C-Verb_2` is 404 while the block is placed). An earlier version of this
  entry flattened all three into "read-back does not catch these", which is
  false for 4 and would send #125 to delayed re-reads for 254, where no re-read
  of that value can help.
- Ordinal 19 was tested directly before 4 and 254, same rig, same slot, same
  protocol, with health sampled every 0.5s: acknowledged, read back, and the
  unit stayed up for 30s. That pair rules out the reading that the NAM module
  is dangerous to place. It does NOT support "roster entry with no object" as
  the class that matters, which the bullet above records as falsified; an
  earlier version of this entry claimed it did.
- A previous draft had cleared 19 on the wrong grounds, that the unit rebooted
  into a rig containing it, which is load-from-disk and not an API write. That
  had already been published to #125 as settled, and was corrected there.
- Six readings of continuous parameters taken off the unit's screen are
  recorded as measurements. The wire takes 0..1 while the published range and
  format describe what the unit displays, and the device names each curve with
  an opaque id and no formula. Nothing here decodes those curves; that is its
  own change with its own provenance.

### Added (HeadRush normalisation tapers, 2026-09-15)
- `config/headrush_tapers.json` plus `tools/build_headrush_tapers.py` and
  `devices/headrush/tapers.py`: the eleven curves that convert between the
  0..1 wire value and the value a HeadRush displays. The device publishes an
  opaque id (`x-options.normalizeAlgo`) and no formula, which stays true of
  the API; the formulas are in the web editor the unit serves, so this is the
  same provenance class as `headrush_topologies.json` and carries
  `api_readable: false`.
- NOTHING IS TRANSCRIBED BY EYE. The generator extracts the vendor's own
  functions, RUNS them under node across 990 points, and commits the results;
  the Python is tested against those vectors rather than against a reading of
  the JavaScript. `Db` and `AllenHeathFaderVolume` are exactly the shapes that
  survive a typo while still returning plausible numbers.
- Six readings taken off a Core's screen are reproduced exactly, formulas
  first. The generator writes nothing if they are not, so a bundle whose maths
  disagrees with hardware fails loudly rather than shipping.
- `normalizeAlgo: 5` is named `Squared`, independently confirming the quadratic
  measured on `Amp.TremSpeed`, and an absent id falls back to `Linear` in the
  vendor's own dispatch.
- Id 3 (`DelayRatio`) is in the enum and in neither table, so it falls back to
  Linear and is recorded as `unimplemented`: an id with no implementation and
  an id implemented as linear are different facts. An id OUTSIDE the enum
  raises, because a firmware publishing an unseen curve must not be silently
  scaled as linear.
- Python and JavaScript disagree at the edges, and the vendor's curves sit on
  them: `Exponential` on a range whose minimum is at or below zero divides by
  zero in `log(hi / lo)`, and `Volume` is `log10(0)` at wire 0. These collapse
  to one typed `NotConvertible` in one place, and a test walks all 990 vectors
  asserting it refuses at exactly the 51 points the vendor cannot express, no
  more and no fewer, and that those points are `Exponential` (45) and `Volume`
  (6). Naming the curves rather than only counting them is the correction:
  independent review found the first version of this entry blamed
  `H3ReverbTime`, which never divides at all because `x > fround(0.99)` returns
  145 first, in the vendor and here alike.
- The grid straddles the joins in `Db` (0.5) and `AllenHeathFaderVolume` (0.25)
  with interior samples either side. Both curves are CONTINUOUS at their join,
  so a sample sitting on it is the same number from either piece and pins
  nothing: a split transcribed as 0.45 produced zero diffs across the whole
  earlier grid. Also from review, and the bound is stated rather than
  overclaimed, since a displacement smaller than the gap to the nearest sample
  is still not distinguished.
- The dispatch is now EXTRACTED rather than retyped into the harness, the
  weakly anchored clamp is checked by behaviour rather than by name, and the
  extraction regexes have their own test file. Nothing exercised them before,
  which was the largest untested surface in a change whose whole value is that
  the extraction is right.
- The vendor's source text is NOT committed. Names and vectors are facts;
  minified third-party JavaScript in this repository would be redistributing
  their code with no licence for it. sha256 prefixes of each extracted
  fragment are kept so a regeneration is verifiable without carrying the code.

### Fixed (capability gates, 2026-09-15)
- The runtime obeys the device contract (#111, the second half of #109).
  `server.py` held a handle typed to `DeviceAdapter` and `Capabilities` said
  what a device declines, and nothing consulted either: a route could call
  any of the 16 methods behind the seven capability sub-Protocols and a
  device that had declined the gate found out on the wire, or one of the 72
  broad `except Exception` blocks absorbed the failure and the route reported
  a silent success. `get_fm9()` now wraps the handle once in `GatedDevice`,
  which checks each gated attribute against the device's declared
  `Capabilities` on access, with the gate table derived from
  `CAPABILITY_PROTOCOLS` at import time rather than hand-listed, so a missed
  call site is impossible rather than unlikely. A decline is its own
  exception, `CapabilityDeclined(capability, method)`, and one handler turns
  it into HTTP 409 with `{"refused": true, "capability", "method", "route"}`.
  Routes whose gated call comes after other writes (rename after select,
  clear-slot, compose, build-scratch, new-preset, apply) check every gate the
  request will need up front, before the undo snapshot and before the first
  write, so a decline arrives with nothing sent.
- The broad-except audit. Every `except Exception` block in `server.py` is
  listed by AST identity in `tests/data/broad_except_audit.json` (72 blocks:
  34 re-raise or convert `CapabilityDeclined` before their handler runs, 38
  carry a one-line reason a decline cannot reach them), and
  `tests/test_capability_gates.py` fails on an unlisted block, a stale entry,
  or an "unreachable" claim over a body that names a gated method. The block
  the issue named, `_will_lay_template`, keeps three distinct outcomes: a
  decline propagates to the 409, a device read failure still answers False,
  and an empty grid answers True. Two re-raises the first pass had put on the
  wrong `try` (the tone-review block in `_plan_for` and the progress callback
  in `_apply_for`, instead of the enclosing planner and starting-chain blocks
  that actually reach the device) were moved to where the JSON said they were.
- Proof by substitution rather than by a hand-picked case: a sentinel device
  (`tests/sentinel_device.py`) declines every gate and raises if any of the
  16 methods is reached; all 83 registered routes are driven through
  TestClient from a request table the test checks is complete, with the
  planner backends, the network and the AI settings stubbed and the
  TONECOMMAND_DEBUG pair driven with the variable unset. No gated method
  fires, every route that needs a declined gate answers the 409 by name, and
  every other route answers exactly as it did against the simulator in a
  baseline run. The same run on a recording sentinel asserts ARCHITECTURE.md
  invariants 1, 2, 5 and 6 survive gate insertion: a decline arrives with
  zero device writes at both method and wire level, a plan without its
  reviewed revision transmits nothing, no route can reach a firmware or
  bootloader message, the undo snapshot precedes the first write, and Pedal 1
  is never bound or cleared.

### Added (share this error, 2026-09-14)
- Settings gains a SHARE THIS ERROR panel (#108). Until now a failure left the
  player with nothing to hand over: the scrubbed local log from #107 existed
  but had no way out, and the two planner-failure paths in `server.py` were
  not even writing to it, so "errors are logged locally" was unused
  infrastructure. Both paths now call `diagnostics.log_error`, and a new
  `GET /api/diagnostics/share-package` returns the scrubbed package (title,
  body, pre-filled GitHub issue URL, entry count) without making any network
  call, proven by a test that patches `urlopen`, `webbrowser.open` and
  `socket.create_connection` to fail if touched. In the drawer the first click
  only fetches and shows the whole scrubbed body for reading; a second button,
  which is not on screen until then, is the single code path that opens the
  issue URL in a new tab, and a test parses the inline script to prove it.
  Nothing is posted until the player presses Submit on GitHub. No telemetry.

### Added (HeadRush grounding, 2026-09-14)
- `config/headrush_amp_models.json`: every HeadRush amp-model ordinal mapped to
  the real amplifier the manufacturer says it emulates. 101 ordinals across the
  `Amp` and `ReValver Amp` blocks, 100 described, 1 recorded as unattributed.
  Generated by `tools/build_headrush_amp_models.py` from two artifacts that are
  themselves generated: the vendor's published model list, and the device's own
  self-description fetched over its HTTP API, which is what supplies the
  ordinals. Same move as #2 for FM9 amps and #14 for cabs.
- Grounding data needs no adapter, no device handle and none of the contract
  work in #109, which is why #33 put it first. It documents what a second
  device's roster means whether or not an adapter ever follows.
- The one ordinal the vendor does not describe is stored as `model: null` with
  a reason rather than omitted or inferred, and the generator REFUSES to build
  when an ordinal has neither a catalog entry nor a declared absence. Measured
  against `config/amp_models.json`, fuzzy matching would fill those gaps with
  confident nonsense: Vox AC30 onto AC15 at 0.80, Fender Dual Showman onto
  Bassman at 0.73. A grounding file that is confidently wrong is worse than one
  that is short.
- No cross-map to the FM9 roster. Both catalogs name real amplifiers, so a
  pivot looks like string matching and is not: exact matching after
  normalisation finds 4 of 100. Cross-device translation needs a
  human-confirmed mapping and is its own piece of work.
### Security
- **A clarifying question could ship alongside actions anyway.** The prompt
  already told the planner "actions must be empty when clarification is
  set", but nothing in code enforced it, so a model that ignored the
  instruction could return both: the UI would show the question in the
  conversation while still proposing the actions for confirm/send.
  `fm9/planner.py`'s `_validate` now forces `actions = []` whenever
  `clarification` is truthy, unconditionally (#72).
- **An open-ended, undecided message went straight to the build path.**
  `requestRoute()` (ui/index.html) only ever classified a first-contact
  message as `source`, `build`, or `modify`; a message with no explicit
  build/change trigger yet ("not sure what I want", "any ideas?") fell into
  `modify` and was sent straight to the planner instead of the
  conversation. `requestRoute()` now recognises open-ended phrasing and
  routes it to chat first (#71).

### Added
- **Never a bare amp+cab preset.** config/tone_rules.md's own "bland test"
  (rule 14) is now a real, enforced gate rather than prose a build could
  quietly fail: `fm9/tone_review.py` rule 16 fails a scene the plan leaves
  with zero engaged effects and no boost, `bland_test_passed` rides on the
  plan result, and the UI will not let CONTINUE TO CONFIRM proceed past it
  (#96).
- **Every build leaves an EQ fine-tune handle.** `tone_review.py` now
  tracks PEQ/GEQ engagement and warns when a build leaves no engaged EQ
  block anywhere, so a player is nudged toward a real post-build
  adjustment handle. A warning rather than a hard fail, the same call
  already made for rule 10's lead margin (issue #65): several presets in
  the professional reference pack gig fine with no EQ block at all (#97).
- **Conflicting requests get named, not silently resolved.** A curated,
  deterministic table (`fm9/request_tension.py`) recognises tonal
  descriptor pairs that genuinely pull in opposite directions on an FM9
  ("tight" vs "warm/dark", "dry" vs "ambient", ...), each with a documented
  lean cited to a specific tone_rules.md rule, and surfaces the tension in
  the planner's context for that request instead of letting one reading
  win with no explanation (#98).
- **Retrieval over the full cab catalog.** The planner's static reference
  only ever carried a curated, deduped slice of bank 3 (issue #45); the
  other ~2,200 factory cab entries across banks 0 and 1 were invisible to
  it no matter what a player asked for. `full_cab_catalog_search`/
  `cab_retrieval_context` (server.py) search the whole catalog on demand
  and append a match to that turn's context only when the request actually
  names something the curated list doesn't carry (#6).
- **Flanger/phaser/wah are marked "no source found", not silently absent.**
  Issue #5's own gate is "if no usable reference exists for a family,
  report that and stop for that family, never guess"; before this, an
  unmapped family just wasn't in `config/effect_type_models.json`, which
  looked identical to "nobody checked yet". `unmapped_no_source` now
  records the reason per family, and the planner reference states it by
  name (#5).
- **Local, secret-scrubbed error logging.** `fm9/diagnostics.py` logs
  structured JSON-lines entries to a local, per-machine file, scrubbed on
  write against Anthropic/generic API-key and Bearer-token shapes and
  `*_API_KEY`/`*_TOKEN`/`*_SECRET`-style assignments, pruned to a 14-day
  retention window. The module makes no network call of any kind, so
  nothing is uploaded anywhere by default (#107, Epic H).
- **Voluntary "share this error".** `package_for_sharing()` builds a
  pre-filled GitHub issue (title, body, URL) from the scrubbed local log
  for a player to review; it never sends anything itself, only a click on
  the URL does (#108, Epic H).

### Changed
- **The device contract stopped being decorative, so a second device can
  finally be written against it.** ToneCommand declared a `DeviceAdapter`
  Protocol and a `Capabilities` mechanism whose whole purpose was to let a
  device say what it cannot do, and then consulted neither at runtime:
  `server.py` did not import `Capabilities` at all, and `conformance()`
  checked the FM9 against a contract derived from the FM9, since `SimFM9` is a
  factory returning a real `FM9`. Passing therefore proved self-consistency,
  not portability. Measured on the way in: routes reached 35 distinct names on
  the device across 96 call sites, 24 of them absent from the 14-method
  contract, three of those private. `fm9/adapter.py` now promotes the five
  that were plain asymmetries (`get_param_display` had a setter and no getter,
  `scan_slots` is the bulk form of `slot_name`, plus `set_params_batch`,
  `scene_name` and `firmware_label`), and puts the rest behind five capability
  sub-Protocols (`ChainEditing`, `Modifiers`, `FileInstall`, `Renaming`,
  `SceneSlots`) because `typing.Protocol` cannot express a conditionally
  required member and requiring them of every adapter would force a device to
  implement a grid it does not have. `conformance()` now also checks the
  gates, so declaring a capability you cannot honour fails instead of
  surfacing when a user tries it. `tests/stub_device.py` is a second,
  structurally distinct implementation that opts into some sub-Protocols and
  declines others. Runtime enforcement of the gates is #111.
- **Chain control is ranked, not a boolean.** `edits_chain: bool` was true
  for the FM9 and for a HeadRush while describing operations that share almost
  nothing, which is the same defect as `has_scenes: bool` and was caught by
  @bschmalz81401 before it shipped (#109). `Topology` is now ranked the way
  `ReadPath` is, so `min()` across a plan's devices gives the weakest link:
  `FIXED` has no say, `SELECTED` chooses from an enumerated set, `CONSTRUCTED`
  draws arbitrary connections. He measured the difference on a HeadRush Core
  at fw `5.1.0.2a63755`: there are no cables on that device at all, the chain
  is fourteen linear slots, and topology is one integer picked from ten
  prebuilt routings. Writing all ten and reading the chain back left every
  slot byte-identical, so the unit publishes the routing names and never their
  shapes, which is why `TopologySelection` promises enumerate, name and
  choose, and deliberately does not promise to describe. `connect_cells` moved
  to `ChainWiring`, gated on `CONSTRUCTED` and absent below it rather than
  present and refusing, because on a device that picks prebuilt routings the
  primitive does not exist. `splice_block`, `plan_splice`, `find_donor_slot`
  and `read_grid` left the contract at any flag level: splice is a workaround
  for two FM9 facts (no free pass-through cell before the amp, cables reaching
  only the next column) and `GridCell` is FM9 geometry, so behind a flag every
  future adapter would have had to answer a question it does not have.
- **Scene state is tri-state and slots are addressed by name.** Measured on
  HeadRush hardware by @bschmalz81401 (#33): `has_scenes: bool` was true for
  both devices and described almost nothing they share. `NO_CHANGE` is what
  makes scenes composable, and a boolean model has to invent "absent means no
  change", which loses the difference between a slot nobody touched and one
  deliberately left alone; matching slots by index re-points a scene at the
  wrong block the moment a chain is reordered. The FM9 declares
  `composable_scene_slots=False` and implements none of `SceneSlots`, because
  it stores bypass and channel per scene and has no wire encoding for "leave
  this slot alone". Declining is the honest answer. In the same pass
  `reads_by_slot` split into `reads_slot_names` and `reads_slot_state`, which
  a HeadRush answers differently, and `split_transport` became
  `observes_foreign_writes`, naming what callers need to know rather than the
  mechanism.
- **`server.py` holds a device handle instead of the FM9 class.** The accessor
  and all 11 helper annotations plus the module global named the concrete
  class, so the indirection existed in name only. Private reach-through is
  gone too: the tempo action called `fm9._send` with a frame it built itself
  and now calls a public `FM9.set_tempo`, and the `/api/state` poll path read
  the private `_channels` cache when `b.channels_supported`, the value that
  cache is built from, was already in scope. The one remaining private access
  is in the `TONECOMMAND_DEBUG=1` endpoint and is allowlisted by name.
- **The persistent 152px hero emblem is now a full-screen loading splash at
  520px.** The header logo bump to 64px (below) still read as too small
  against the ask to make the site's logo genuinely big, and a nav icon
  can only grow so far before it fights the sticky header for space. The
  fix moved the "big logo" moment to where it actually works: a full-screen
  splash (site/build.py, site/theme.css `#splash`) shows the emblem at up
  to 520px, centered, once per browser session, then fades to reveal the
  page beneath. It skips instantly on a repeat visit in the same session
  (sessionStorage), on the first click/key/tap (site/fx.js), and outright
  under `prefers-reduced-motion`; the fade-out is plain CSS so it still
  resolves even with JS disabled. Replaces the `.mark` pulse entirely.
- **The header logo grew from 40px to 64px.** It is the one logo visible on
  every page of tonecommand.com, and at 40px it read as a mini icon next to
  the wordmark instead of a real logo. site/build.py's shared header
  template now renders it at 64px; the sticky header absorbs the extra
  height without any other layout change.
- **The emblem is back, loud and clear, at the top of the site.** The
  nam9000-style redesign replaced the hero's mark with the interface
  screenshot and left the logo as a 36px header icon, easy to miss. A large
  glowing version (site/build.py, .mark) now opens the page above the
  tagline, pulsing gently in the site's own cyan and purple; the header icon
  grew to 40px too.
- **Dropped the "if you have to switch to FM9-Edit, we have already lost"
  line from docs/INTERFACE.md.** It carried the 0.3.0 release's framing
  forward as a present-tense rule, but the premise behind it (that FM9-Edit
  destroys the edit buffer) was tested afterward and found wrong, see
  "Running beside FM9-Edit" in docs/SETUP.md. What is still true stays:
  every panel is a control surface, not a readout.
- **"Humans in command" opens with the case for it, not just the rule.**
  Everyone braces for machines to take over; they already did, and every
  guitarist has spent decades learning a device's language to operate it.
  ToneCommand inverts that: the machine learns yours. The existing safety
  prose (no autonomous mode, blast radius, "ears: pending, always") now
  follows as the proof the reversal is safe, instead of standing alone.

### Added
- **`config/headrush_schema.json`, the unit's own self-description, committed
  (#33 phase 2).** Generated by `tools/build_headrush_schema.py` from
  `GET /api/v1/subtree/` through the phase 1 client, never hand edited. A
  HeadRush Core at fw `5.1.0.2a63755` answers with **309 objects**, which reduce
  to **161 distinct metas**, and the file stores each meta once under a content
  hash with a path map beside it. That dedup is lossless and deliberately not a
  twin-specific transform, because the sharing is not only twins: ten groups are
  not `base`/`base_2` pairs at all. The largest is ten paths spanning **five**
  model families, `Green_JRC-OD`, `Greener`, `K_Drive`, `S1_Drive` and
  `Slab_O_Meat`, all sharing one meta; `Black_Wah`/`Shine_Wah` and
  `Amp_Clone`/`Pedal_Clone` are others. Different models, identical parameter
  surfaces, which means a parameter set is not an identity for a model and
  phase 4 must not treat it as one. That sentence is derived from the data
  rather than typed, which is how the five families were noticed: the
  hand-written version of it said two. **Property values are not
  committed.** The subtree response carries the owner's live rig state beside
  the schema, which is preset data `AGENTS.md` says not to commit, so values are
  dropped and an explicit allowlist carries back the four that are device
  capability rather than owner state: the 278-entry `ModuleTypes` roster that
  `Chain.ModuleType{n}` indexes into, the two block-category vocabularies, and
  the firmware string. 9055 property values were present and 4 were kept. The
  generator refuses rather than guesses, exiting non-zero and writing nothing if
  the firmware cannot be read or a roster is absent or the wrong shape, because
  a snapshot missing its roster still looks complete while having lost the only
  thing that says what a slot holds. Completeness is pinned by a test, not just
  self-consistency: a snapshot that dropped two thirds of the tree still agreed
  with itself in every other check. It also corrects the record: this API does
  **not** mark twins. #109 said the `_2` objects carry `"twin": true`; no meta
  in the file has any such field, and the only "twin" in it is the cabinet name
  `California Twin 212 Combo`. `object-meta` was also compared against
  `subtree` by hand and came back byte-identical for the same path; that one is
  recorded as a hand measurement rather than something the suite re-checks.
  That flag is in the editor bundle, not on the API. The measured sentences in
  the artifact's own `notes` are computed from the tree being written, so a
  regeneration on new firmware cannot leave the previous unit's numbers sitting
  beside the new data.
- **`devices/headrush/client.py`, the HeadRush transport (#33 phase 1).** HTTP
  and mDNS only: the unit self-describes over unauthenticated HTTP on port 80
  (`subtree`, `object-meta`, `object-properties` read and write,
  `object-method`, and a `ws://` change feed), so there is no protocol to
  reverse engineer and this layer is small. It knows nothing about
  ToneCommand, which a test pins by parsing its imports: no `DeviceAdapter`,
  no `Capabilities`, no effect ids, no `validate_action`. Nothing calls it
  yet, on purpose. Three device facts measured on a HeadRush Core, fw
  `5.1.0.2a63755` (#109), are what the module mostly consists of, and each
  reads as an indistinguishable connection failure when it is got wrong: the
  unit publishes both an A and an AAAA record and which one the resolver
  returns varies by process, so a link-local answer falls back to the hostname,
  because a zone has no spelling `urllib` accepts in an http URL (`getaddrinfo`
  does return the scope, unlike Node's `lookup`, and the module says so rather
  than repeating the Node fact); a
  `*.local` name costs about 5 s per lookup against about 130 ms of real work,
  so the name is resolved once and reused, and the first lookup asks for IPv4
  alone because the dual-family query waited 5008 ms to return an A record it
  already had; and writes answer `200` with an EMPTY BODY, so parsing a reply
  as JSON throws on every `PUT`. Failures are classified by exception type and
  errno rather than message text, which is what keeps the unit's own `504` on
  a wrong-argument method call from being reported as a device that is not
  answering. Resolver and HTTP opener are both injected, so the whole file is
  tested with no unit on the network and no new runtime dependency: resolution
  is `socket.getaddrinfo`, which is what the measurements were taken through,
  and HTTP is `urllib.request`, as every other runtime HTTP path in this repo
  already is. Writes remain immediate and unguarded at this layer; the
  `object-method` allowlist is phase 4's deliberate decision, per #33.
- **A recipe can cite a real NAM Architecture 2 (A2) capture as its tone
  target (#18).** NAM A2 (TONE3000 + NAM's creator, launched June 2026) is
  becoming a cross-vendor capture interchange format, and issue #18 asked
  ToneCommand to speak it as data first: a recipe's new optional
  `tone_target` (`{"source": "TONE3000", "capture_id": ..., "note": ...}`)
  names the real capture a build approximates, honest about the direction
  of the approximation: on an A2-capable device the capture IS the tone, on
  the FM9 the recipe's own steps are the grounded approximation.

  A citation is only as honest as what backs it, so `config/nam_capture_models.json`
  is a new facts-only grounding sidecar (fm9/grounding.py's existing
  envelope), harvested for real from TONE3000's own API by
  `tools/build_nam_captures.py`: real title, the capture author's own
  stated gear identity, creator and verification status, usage signals,
  licence and a checkable URL. TONE3000 exposes no per-capture accuracy
  metric (checked directly against their API), so the sidecar says that
  rather than inventing one; ranking captures by evidence is future work,
  this pass only refuses a citation that is not real. `tools/replay_recipe.py`
  rejects an ungrounded `capture_id` before a device or simulator ever
  connects, and `service/worker.js`'s public recipe-submission gate accepts
  the same well-formed shape a stranger might submit. New example:
  `recipes/mesa-mark-v-a2-reference.json`, citing FM9's own grounded "USA MK
  V Green" (Mesa Boogie Mark V clean) against a real capture of that same
  amp.
- **Current is the permanent A side of the cab comparison, and you can
  choose a B.** The panel used to have a B side and no A: three candidates
  you could preview, and no way to hear or see the cab they were being
  compared against except as a sentence. Current is now a row of its own,
  previewable when it is one of your own IRs and honest about having nothing
  to play when it is not.

  Each alternative that is actually on the FM9, in a slot you have linked,
  carries USE THIS. Choosing one is an edit to the plan and goes through the
  same path an edited number does: the server re-validates it and mints a
  fresh digest, so Confirm cannot arm against the plan you were shown before
  the change. A candidate that is only a file in your library says so rather
  than offering a slot that does not exist.

### Fixed
- **Installing an IR into a linked slot kept the old file's provenance.**
  Protecting a link across a rename created this: the install path is a
  rename call, so writing different audio into a linked slot left the old
  `source` and `digest` in place. The file on disk was untouched, the digest
  still matched, and the slot went on anchoring "x dB from current" against a
  capture it no longer contained. An install and a rename are now different
  calls, because they mean different things.
- **A cab's display name could become a hard search constraint.** A measured
  user slot has no gear identity, and the preserve fallback ended at the
  slot's name, so one labelled "Soldano SLO30 - Emil Rohbe" excluded every
  Mesa, Marshall, Orange and Friedman in the library before ranking, and
  reported the label back as if it were gear. A measured anchor constrains
  with its curve, which is better evidence than a guess at the words.
- **An unreadable cab target was hidden whenever any row came back.** The
  panel showed the reason only on an empty list, and a name-fragment match
  usually returns rows, so filename coincidences were presented as the
  answer. Those rows are now labelled as name matches, not alternatives.
- **A blank preservation question vanished on the wire**, which the library
  read as "apply the constraint unconditionally", so a build with an empty
  prompt filtered on the loaded cab and reported preserving nothing. An
  older library that cannot be asked at all now says so instead of being
  read as a no.
- **A user cab installed from a Fractal `.syx` could never be linked**: the
  file search was filtered to `.wav`, which excluded exactly the format the
  installer writes.

### Added
- **Link a user-cab slot to the file it holds.** The `measured` comparison
  state has existed, been tested, and been unreachable by any route the
  product offers: every install path writes a bare display name, and the
  whole `/api/user-cabs` surface had no client in the page at all. So a
  player with thousands of analysed IRs and one of their own cabs loaded was
  permanently told "nothing is loaded to compare against", with no way to fix
  it. The cab panel now offers the fix where it reports the problem: search
  your library by name, pick the file, and the slot becomes a real reference.

  The player picks. Searching by name and taking the top hit is ranking, and
  ranking cannot establish identity: two captures of one product share every
  token, so the best match can be plausible and wrong. A link is refused
  rather than recorded when it cannot be stood behind, because a slot that
  claims an anchor and produces no comparison is worse than no link. And the
  reply says what a link does not prove: nothing can read the IR back off the
  FM9, so the device side is your word.

### Fixed
- **Renaming a linked slot threw the link away.** `set_name` overwrote the
  whole entry with a bare string, so typing a nicer name silently stopped the
  slot being an anchor and said nothing.

- **A measured anchor was never asked to keep the cab.** Only a gear-anchored
  Current received the preserve constraint, so "keep the same cab, just
  darker" against one of your own IRs got curve proximity and nothing else.
  The nearest curve in the library can be a different size with a different
  speaker; "keep the same character" is a claim about the gear, not about a
  distance.
- **The model's words could switch on a hard constraint.** The preservation
  question was the prompt, the model's summary and the model's `cab_need`
  concatenated, so a summary containing "similar" preserved the cab for a
  player who never asked. Only the player's words decide now.
- **A stale IR service silently dropped preservation.** It took two requests,
  and a 404 on the first came back as "not asked for" while the second
  answered normally, producing candidates that look fine and ignored the
  constraint. It is one request now, and it cannot half-succeed.
- **An orphan measurement could forge a measured anchor.** `features.json`
  outlives the catalogue it was built from, so a row can survive a rescan
  that dropped the file. Library membership and the presence of a curve are
  now both required.
- **Review hid a listening set it had been given.** The panel returned early
  whenever a plan had no cab action, no amp-voice change and no readable
  loaded cab. The planner may name a cab target without choosing an asset, so
  that plan carries a real listening set and showed nothing.
- **The panel claimed an algorithm that had not run.** A measured Current
  always said "ranked by least change" even when the request named no
  direction and ordinary scoring decided the order.

- **The cab search ran on words no gear matcher could read.** Retrieval fired
  BEFORE the planner, on the player's raw prompt, so "steve vai lead tone"
  scored 0.07 and handed the planner a Soldano SLO30 capture. That is where
  the Soldano actually came from: the planner's own prompt, not the review
  panel. When a request does not parse into gear, the planner is now told
  what the library CONTAINS (counts, speakers, cabinets, mics) and asked to
  name the cab in gear terms; the real ranked search then runs afterwards on
  that translation, where it works. A request that does parse is unchanged.
- **The one property that decides how a cabinet sounds was dropped.** The
  roster records bank 3 slot 42 as a V30 in its `group` field, but the anchor
  emitted only "4x12 RECTO SM57", which parses to a size, a brand and a mic
  and no speaker. Preserving that cab could not reject a Greenback. The
  speaker now reaches the constraint.
- **An empty cab panel gave no reason.** A dead IR service, an unparseable
  request and a genuinely empty shelf all arrived as the same silent empty
  list, which reads as "cabs were never considered". Each now says which one
  happened, and an unparseable request is never reported as an empty shelf.
- **Programming errors still hid as an absent service.** Only `TypeError` was
  separated; `AttributeError`, `KeyError`, `IndexError` and `ValueError` were
  still reported as "the IR library did not answer".

- **Review never showed the cab reasoning it was given.** The plan built a
  constrained listening set on the server and the Review panel ignored it,
  running its own unconstrained `/api/ir/recommend` on the player's raw
  words instead: no reference cab, no preserve constraint, no gear
  translation. That is why a "steve vai" build came back offering a Soldano
  SLO30 capture. Review now renders `cab_selection`, and says which of the
  three anchor states it is entitled to claim.
- **`measured` could be forged.** A user-cab slot became a measured anchor,
  licensing numeric "x dB from current" claims, on the strength of a
  recorded path that merely existed. A record naming `/etc/hosts` with a
  wrong digest came back measured. It now requires the file's bytes to match
  the digest recorded when it was linked, and IRCommand to hold a measured
  curve for that exact path. A library that is off or down means
  gear_anchored, never assumed.
- **Preservation never fired.** "Keep the same character" was read from
  `result["request"]`, which nothing ever set, so it returned `""` on every
  real call and preservation only worked if the model happened to echo the
  word in its own summary. The prompt is now carried onto the result before
  the selector runs, and so is `whole_rig`, which was set one line too late
  and let a whole-rig build preserve the cab it was replacing.
- **A gain word ranked cabs.** `clean` was declared amp-only and was also a
  character rule and a genre token, so it went on rewarding Greenbacks and
  clean-tagged rows through two paths the exclusion never covered. An IR is
  linear: no cab is clean. Amp-only words are now subtracted from character
  and genre as a set, so the next overlap cannot repeat it.

### Changed
- **The preservation cue list has one home.** ToneCommand kept its own copy
  of "keep / same / similar" in `server.py` under a comment saying the
  matcher was authoritative. It was not, it was duplicated. IRCommand's
  parser is asked over a new `/ir/intent` endpoint, so a cue added there
  works here on the next request.

- **The amp and cab audition list was invisible in manual mode.** The manual
  inspector is a fixed panel stacked at 90; the audition popover, also fixed
  so a long name cannot widen it, sat at 40 and rendered behind the sliders.
  Pressing the amp or cab name looked like nothing happened, on exactly the
  screen whose point is auditioning by typing. Found by re-shooting the
  README on the live rig. A test now pins the popover above the inspector.

### Changed
- **Every interface screenshot re-taken on the current UI**, live from a
  connected FM9: the full page, both auditions, the effects panel with its
  bypass and modifier badges and P2 buttons, the blast radius (scene rail
  plus the WHAT WILL CHANGE card), and a health scan. The full-page shot is
  the PLAN stage of a real request through the real planner, proposed and
  not sent. `tools/readme_shots.py` reproduces them. The graphic EQ shot comes from preset 12, found by stepping the unit
  through all 512 presets and reading each chain: 33 carry a GEQ block.

### Added
- **tonecommand.com.** The project has a home that is not a GitHub README.
  `site/build.py` generates the whole site from what the repository already
  says (README, docs, changelog, screenshots, `recipes/`), so the site can
  never drift from the repo, and a workflow republishes it on every push to
  main, which keeps the recipe gallery current as the share service publishes
  new recipes. Hosted on Cloudflare Pages, free tier. Recipes are also served
  as JSON at `/recipes/index.json` and `/recipes/<name>.json` with CORS open,
  and the app now reads the shared catalogue from there first, falling back
  to the GitHub contents API (and its 60-requests-an-hour cap) only when the
  site is unreachable. The share service answers on share.tonecommand.com;
  the workers.dev address still works.

### Security
- **The IR bridge could be pointed at any address.** `fm9/ir_service.py` fetched
  whatever URL it was given, from inside the user's network, and the response
  was fed into the planner's prompt. That is both a server-side request forgery
  primitive and a way for a hostile endpoint to put text in front of the model.
  Loopback only now, validated when saved AND again at use, because the config
  file and the environment variable can both be edited outside the UI. Redirects
  are refused rather than followed off-host, and recommendation text is fenced,
  newline-stripped, bracket-neutralised and length-capped so a crafted filename
  cannot forge an instruction line. `TONECOMMAND_IR_ALLOW_REMOTE=1` is the
  deliberate escape hatch (#53).

### Added
- **The cab search can hear.** IRCommand now measures every cab IR once,
  offline, so `darker`, `brighter`, `more body` and `tighter` are real
  directions rather than words hunted in filenames, and can be answered
  relative to the cab you are on. The review shows match quality in words, the
  measured brightness, and how far a candidate sits from your current cab
  (#61, #63).
- **Blend advisor.** Which of your own IRs combine well with one another, and
  the sub-millisecond alignment each blend needs. On a real library, blending a
  Soldano capture with a V30 4x12 gives +2.19 dB with nothing cancelling at
  +0.271 ms, where the same pair unaligned reads -3.95 dB with 44.7% of the
  band cancelling. Take the shortlist into Cab-Lab, apply the shift, install
  the result as one cab (#62).
- **Previews say how they were made.** Every rendered candidate carries a
  fidelity grade. This renderer uses a fixed synthetic DI and a generic
  saturation stage, so it says `Representative preview`, never "heard in your
  rig", and the grade travels with the audio so the UI cannot overstate it.
  Fractal `.syx` and factory cabs read `ON RIG ONLY`, since their IR body
  cannot be rendered at all (#59).
- **Audition integrity is a contract, not a convention.** Same source, same
  drive, same level, same length, and a seeded DI so repeat renders are
  identical. That is what makes a set of previews a fair comparison of cabs
  rather than three unrelated auditions (#57).

### Changed
- **Cab previews are loudness matched, not peak matched.** Every candidate now
  renders to the same RMS level rather than the same peak, so none of them wins
  a comparison by being louder. Measured on three real library IRs, peak
  matching left a 2.15 dB spread in actual level; it is now 0.00 dB. A render
  that would clip is scaled down and says so, rather than presenting a broken
  match as a fair one. `GET /api/ir/audition` reports the achieved level and
  whether the match held.
- **An empty tone review no longer poses as a pass.** A plan is a delta, so any
  parameter it does not set is unknown and its check is skipped. One green
  result therefore meant three different things: nothing wrong, nothing
  checkable, or no scene role inferred. Reviews now report coverage, and the UI
  says `no issues in the N checks I could run`, or says plainly that nothing
  could be checked (#54).
- **Review and Send now refer to the same plan.** Editing a value in Review
  used to mutate the browser's own copy after the server had validated it, so
  Confirm could show guidance for a plan that no longer existed. An edit is now
  a new revision: it re-validates server-side, returns fresh findings, and mints
  a new digest. Send names the digest it believes it is sending and is refused
  if it does not match what the server approved (#55).
- **Read-back no longer claims more than it proves.** The device layer said
  `verified by read-back`, which reads as confirmation of sound. It now says
  `read back on the unit`. A new proof vocabulary keeps sent, read back, sound
  checked, closer to target, your pick and kept strictly separate, and nothing
  can be called closer to target without a measurement. `Better` belongs to the
  player and is never asserted by the system (#58).
- **A guided correction may not send without a recovery snapshot.** A failed
  snapshot still lets a manual edit through, since the player asked for it and
  can hear the result. A correction the system proposed from a measurement is
  refused instead (#60).
- **Hear the cab before you commit it.** REVIEW now shows the cab the build
  lands on, plus alternatives from your own library, each with a PLAY button and
  a drive selector (clean / crunch / lead / high-gain). Previews render in the
  browser from a synthetic DI: `GET /api/ir/audition`. The chain is DI ->
  saturation -> cab, deliberately in that order, because an IR cannot contain
  distortion and auditioning a high-gain cab with a clean source misrepresents
  it. Only WAV IRs render; Fractal `.syx` and factory cabs say ON RIG ONLY,
  since their IR body is an encoded device format this codebase does not decode.
  Reading is fenced to the IR library by `ir_service.safe_ir_path` (symlinks
  resolved before the containment test), so the endpoint cannot be turned into
  an arbitrary file read (owner, 2026-09-07).
- **The planner now talks about the cab it picked.** When IRCommand is on, the
  best matches from your own library are passed into the planner's context, so a
  build says which IR it found and why it suits the amp and era instead of
  discussing cabs in the abstract. Silent no-op when IRCommand is unset, and a
  failing lookup can never take a build down.

### Changed
- **tone_rules 3a: an IR cannot contain distortion.** New rule spelling out that
  an impulse response is a linear snapshot, so there is no "driven IR" or "clean
  IR", and a cab must never be justified by the gain it was captured at. Builds
  now use ONE cab for the whole preset, since scenes differ by gain, drive, EQ
  and level, all upstream of the cab. The single exception is a clean scene,
  which is cab-dominated and may take its own brighter channel: at most two
  cabs, never one per scene.
- **Optional IRCommand cab-recommendation bridge, off by default.** A new
  Settings > IR SERVICE field points ToneCommand at a local IRCommand service
  (a separate local tool that catalogues and matches your own IR library). Empty
  means off and nothing changes: factory cabs, no IR step, no network. When set,
  ToneCommand can ask IRCommand for the best cab IR for a tone. `GET
  /api/ir/status` and `GET /api/ir/recommend`, both no-ops when unset; the client
  never raises, so a missing or broken service can never break a build. The url
  saves like the tone folder and the `TONECOMMAND_IR_SERVICE` env var pins it for
  operators (owner, 2026-09-07).

## 1.2.2 (2026-09-06)

### Changed
- **A bad release can no longer break the updater.** Before it will restart, an
  update now proves the new code actually loads (imports and builds the app) in
  a throwaway check. If the pull, the reinstall, or that check fails, the
  checkout is reverted to the version that was already running and the failure
  is reported, so the working server is never stopped for code that has not been
  shown to start. If a restart somehow does not come back, the page shows a
  plain recovery step instead of a blank error (owner, 2026-09-06).

## 1.2.1 (2026-09-06)

### Changed
- **Updating is now fully hands-off.** The update button lives in the banner
  AND in Settings, both show a progress bar, and the app pulls, reinstalls, and
  **restarts itself** so the player never touches the terminal. The restart is
  graceful (never a hard kill) and releases the FM9's MIDI port first, so it
  cannot leave a poisoned port; the browser watches a per-launch boot token and
  reloads onto the new version on its own once the fresh server answers (owner,
  2026-09-06).

## 1.2.0 (2026-09-06)

### Added
- **Version awareness and one-click updates.** Settings shows the running
  version and a CHECK FOR UPDATES button. On launch the app asks GitHub for the
  latest release (cached, silent when offline) and, when it is behind, shows a
  banner with the new version, a release-notes link, and the exact upgrade
  commands for the player's OS. On a clean checkout on the main branch it also
  offers a one-click UPDATE button that runs `git pull` and the reinstall for
  you. It never pulls or restarts on its own, is blocked during gig lock, and
  refuses a checkout with local changes or on another branch, so a live FM9
  session is never yanked out from under you. `TONECOMMAND_VERSION_OVERRIDE`
  reports a chosen version so the update flow can be exercised on demand
  (owner, 2026-09-06).

### Changed
- **Install docs make all three OSes unmissable.** The README Install section
  now shows macOS, Windows and Linux with visible commands instead of hiding
  Windows behind a link, and SETUP.md gains a proper Linux section (owner,
  2026-09-06).
- **A rulebook guardrail so a delay never hides the note again.** From a live
  SLO build where the delay ran so wet the dry note was inaudible: the dry must
  always be heard, a pedal on a wet mix must never reach a dry-killing value,
  effects bypass Thru not Mute, and never claim a structure you do not build
  (owner, 2026-09-06).

## 1.1.0 (2026-09-06)

A full visual redesign of the interface, and the review stage is now editable.

### Added
- **Inline value editing in Review.** Every numeric parameter with a published
  range is now an editable field in the AFTER column. Type a new value and it
  lights amber the moment it differs from the plan; on commit it clamps to the
  block's real min and max, and an "edited" chip resets it to the planned value.
  The number you set is exactly what the confirmed send transmits, through the
  same read-back-verified path, so the plan is a starting point you can dial in,
  not a take-it-or-leave-it (owner, 2026-09-06).
- **Prev/next preset arrows.** The preset field is wider so a full name reads,
  and flanking arrows step the loaded preset on the FM9 without opening the list
  (owner, 2026-09-06).

### Changed
- **A rack/HUD redesign of the whole interface.** The five-stage flow (Request,
  Plan, Review, Confirm, Send) is now a row of angled hexagon step-tabs with an
  icon each, lit on the active stage and turning to a green check once a stage is
  done. Machined panels, a brushed faceplate and footer, a labelled command
  shelf, and the signal chain shown by default, centred and enlarged so it uses
  the full width instead of hugging the left. The layout, the scene rack, the
  review table and the confirm gate are the same ones as before, reskinned; no
  functionality was removed, and the full test suite stayed green throughout
  (owner, 2026-09-06).
- **Holds up on a short desktop.** On a low screen the live signal chain yields
  its space so a populated Review list is never squeezed to nothing (owner,
  2026-09-06).

## 1.0.0 (2026-09-05)

First stable release. ToneCommand builds a gig-ready, multi-scene FM9 preset
from one sentence, you review and confirm every parameter change, and it lands
on the hardware verified by read-back. Everything below shipped into 1.0.0.

### Added
- **One-tap +Create: a blank canvas, always ready.** A single button lays a
  fresh starter rig on a free slot, or clears the loaded edit buffer on a full
  unit, so there is always somewhere to build. It blinks while it works and
  focuses the composer when the canvas is ready. Blocked in gig mode, refused
  cleanly when there is nowhere to build. GitHub #44 (owner, 2026-09-05).
- **Both expression pedals, bound by name.** "Put global volume on Pedal 1 and
  wah on Pedal 2" now works for either onboard pedal, not just Pedal 2. Pedal 1
  was decoded on hardware (source ordinal 10) and productionized behind a
  bind-pedal action, with a full modifier bind that survives store and reload;
  unbind understands both pedals. All thirteen shipped FM9-AI presets were
  audited and normalized to Pedal 1 = global volume, Pedal 2 = effects. GitHub
  #11 (owner, 2026-09-05).
- **Pick a cabinet by name in a build.** "Put a 4x12 V30 on the rhythm" is a
  first-class planner action now, so a build chooses the cab instead of leaving
  the template default. GitHub #45 (owner, 2026-09-05).
- **A prebuilt starter template, laid in one pass.** A from-empty build lays the
  whole chain it almost always wants (input, drive, amp, cab, delay, reverb,
  output) left to right at once, extras bypassed until a tone calls for them,
  so no cell slides and no block splices in one at a time. Laid and verified on
  the real unit every build, never a stored file that could drift. GitHub #47
  (owner, 2026-09-05).
- **A bounded repair pass.** When a planned action fails verification, the
  planner gets one scoped chance to correct it instead of the build stalling.
  GitHub #39 (owner, 2026-09-05).
- **A health scan after every structural build.** The moment a build lands, a
  scan flags a dead or duplicated scene so a clone that came back wrong is
  caught immediately, not at soundcheck. GitHub #51 (owner, 2026-09-05).

### Changed
- **Faster, more reliable verification.** Same-block parameter writes are sent
  as one burst and confirmed in a single bulk read instead of one round-trip
  each, with any straggler retried through a displayed write, so nothing is
  ever written blind. The slow, timing-fragile part of a build is gone (owner,
  2026-09-05).
- **A tone rulebook the planner reads on every build, dialed in by ear.** The
  clean/distorted loudness balance was set on real hardware: clean amps make far
  less raw output so their level runs hot while distorted scenes run well below,
  a 25 to 30 dB spread for equal perceived loudness. Cleans ship loud, leads
  out-saturate the rhythm, no scene ships silent, and the four-amp-channel hard
  limit is stated so the planner never promises a fifth amp voice. Validated by
  a cold cross-genre metalcore build (owner, 2026-09-05).

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
- **A cleaner, less cluttered UI for a non-technical player.** Scene names now
  read in full across a full-width row with the signal chain stacked below and
  hidden by default (a "View signal chain" button reveals it). Less jargon (the
  chain legend and prompt hint are plain language), crisp SVG icons in the
  footer instead of emoji, a single settings gear (AI settings open from the
  "using <model>" tag), sliders gain -/+ nudge buttons and open expanded for
  precise tweaks, and the conversation starts fresh on every reload. Several
  overlaps were fixed (a scene "will change" marker is now a dot, not text over
  the name; the confirm-stage warning no longer overlaps its checkbox; the
  build-progress panel no longer shows the prompt through it) (owner,
  2026-09-04).
- **A loudness guardrail in the tone rulebook.** Perceived scene volume is the
  whole gain stage, not just the amp level: parallel wet blocks sum, a boost
  stacks on the amp, and no scene may be more than ~4 dB louder than the rhythm
  scenes. Came from a build whose two lead scenes stacked a boost and four
  parallel wets and came out painfully loud (owner, 2026-09-04).

### Added
- **Both new features now have a natural-language front door, tested end to
  end on hardware.** Reorder and scene-aware copy existed only as API
  endpoints, with no way for a person typing a prompt to reach them. Now:
  reorder is a first-class planner action, so "put the delay before the
  reverb" plans a reorder and applies it (verified live: the planner emitted
  the reorder, the grid read back delay before reverb, path alive); and "copy
  the delay and reverb from the Periphery tone" routes through a new
  copy-effects NL parser (server-side and unit-tested) that reads the source
  and effects out of the sentence and runs the scene-aware copy (verified
  live: 668 settings written, 0 failed). The parse defaults to delay and
  reverb when no effect is named, and says so (owner, 2026-09-04).
- **A test report generated from a real suite run, offline, not a hand-typed
  page.** tools/gen_test_report.py runs pytest with junitxml and renders an
  HTML report whose every number comes from that run; if the suite is red, the
  page is red. Writes to a local folder, source junit.xml beside it. Replaces a
  report whose figures were typed by hand and had drifted (owner, 2026-09-04).
- **Reorder a block into the correct signal-chain order.** "Put the delay
  before the reverb", "drive before the amp": the planner adds blocks and
  copy/compose lifts them, but nothing moved them, so a faithful copy of an
  ambient tone could land delay after reverb. Reorder moves one block relative
  to another on the same row and proves Input->Output still walks before
  calling it done; a move it cannot cable correctly (cross-row, over a gap, or
  into a cross-row feed) is refused by name, never guessed. Reuses the splice
  and settle-aware verify already proven on hardware. Round-trip
  hardware-confirmed on a real eight-block preset row (owner, 2026-09-04).

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
