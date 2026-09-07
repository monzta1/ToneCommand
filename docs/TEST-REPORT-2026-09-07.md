# Test report, 2026-09-07

Scope: everything built on 2026-09-07 across ToneCommand (`fm9-tone`) and
IRCommand (`ir-command`), plus an adversarial pass written specifically to
break that work rather than confirm it.

Status: **all suites green in both orderings.** Six defects were found and
fixed, four of them in code written the same day. One issue I filed turned out
to be my own doing and is written up as such (5.1). One genuinely open item
remains (5.2).

---

## 1. Headline numbers

| Suite | Result | Time |
|---|---|---|
| ToneCommand, deterministic order | **1329 passed** | 7m 36s |
| ToneCommand, random order | **1329 passed** | 7m 39s |
| ToneCommand, before today's work | 1180 passed | ~7m 30s |
| IRCommand | 106 passed | 4.1s |
| Adversarial edge cases (both projects) | 97 passed | <1s |

About 190 tests were added today. The adversarial suites
(`tests/test_edge_cases.py` in both projects) are the interesting ones: they
were written to find failures, and they did.

---

## 2. Defects found by the adversarial pass

These were all found AFTER the feature work was committed and passing. Each is
a real defect, not a test problem.

### 2.1 A malformed URL crashed the IR config endpoint (ToneCommand)

`urlparse("http://[bad/").hostname` raises `ValueError` itself. `check_url`
caught only what it raised deliberately, so a raw `ValueError` escaped.
`/api/ir/config` and `status()` catch `UnsafeServiceURL` specifically, so a
malformed address produced an **unhandled 500** rather than a clean refusal.

Severity: moderate. It is a denial-of-clarity rather than a breach, but it is
in the middle of the security boundary added the same day for #53.

Fixed: the parse is wrapped, and `check_url` now raises `UnsafeServiceURL` and
nothing else.

### 2.2 The #54 fix committed the exact error #54 was about (ToneCommand)

`tone_review.coverage()` counted a known scene ROLE as a check that ran. A
scene with a role and no parameter values at all therefore reported
`status: verified` while nothing had actually been checked.

That is precisely the overstatement the function exists to prevent, reintroduced
one level down. A role is not a check; it is the precondition for one.

Fixed: at least one VALUE must be observed before the status can be `verified`,
and the `why` line says so when only roles are known.

Severity: high, because it silently defeats the feature's whole purpose.

### 2.3 Mismatched tonal curves measured as identical (IRCommand)

`curve_distance` used `zip`, which stops at the shorter input. Two curves that
differed ONLY past the shorter one's length measured `0.0`, i.e. identical.

Demonstrated:

    32-band vs 4-band, both flat        -> 0.0
    differing only past band 4          -> 0.0   (should be "very different")

In `_measured_diversify` that would silently drop a genuinely different
candidate as a near-duplicate, which is the opposite of what #63 is for. Not
reachable today, since every curve is 32 bands, but a stale or truncated
`features.json` would reach it.

Fixed: curves of unlike length are incomparable and return infinity, so the
safe direction is "keep both" rather than "these are twins".

### 2.4 The pack-demotion rule condemned small honest packs (IRCommand)

Probing the boundary rather than testing an example:

    pack of  3 with 1 clip  (33%) -> 2 cabs demoted
    pack of  6 with 2 clips (33%) -> 4 cabs demoted
    pack of 10 with 3 clips (30%) -> 7 cabs demoted

A three-file pack shipping one demo file lost both of its cabs. Plenty of
legitimate packs ship a demo, so the ratio alone was too eager.

Fixed: a pack is now judged only when it has at least 5 audio files AND at
least 3 clips AND meets the ratio. Verified against the real library: the
metronome pack that motivated the rule (14 non-IR of 20) is still condemned,
and zero junk returns to the cab pool.

### 2.5 and 2.6 Found earlier the same day, during feature work

- `analyze.blend()` assumed a fixed FFT size and raised `IndexError` on any
  input shorter than `NFFT`.
- `_axis_stats` required more than 8 analysed files, so measured axes silently
  scored nothing on a small library, failing open rather than loudly.
- The blend shortlist rejected every useful partner by comparing RELATIVE band
  energy across files. Band values are normalised per file, so a brighter
  partner always shows less relative low. Removed.
- `convert.trim()` divided the raised-cosine window by `fade` instead of
  `fade - 1`, leaving the final sample at 6e-4 instead of zero. That residual
  step is exactly what convolution turns into a click. Real IRs hid it because
  their tails are already silent.

---

## 3. What the adversarial suites cover

### ToneCommand, `tests/test_edge_cases.py` (57 tests)

**URL security.** Hosts that merely mention loopback are refused: credentials
hiding the real host, loopback as a userinfo decoy, `localhost.evil.com`,
loopback only in the path, query or fragment, and scheme-relative URLs. Genuine
loopback forms are accepted including uppercase, all of `127.0.0.0/8`, and
`[::1]`.

Obscured loopback forms (`http://2130706433`, octal, `127.1`) **fail closed**
and are pinned as such. They really are loopback and we refuse them; refusing
something safe is the harmless direction, and the test exists so a future
loosening has to be a decision rather than an accident.

**Filesystem boundary.** A symlink inside the library pointing outside is
refused. So are the library root itself, a missing root, and non-WAV
extensions including `cab.wav.txt`.

**Hostile audio.** Silent files, single-sample files, empty data chunks,
truncated headers, DC slabs. Output is asserted finite and unclipped. Unknown
drive names fall back rather than crash. Absurd durations (negative, zero,
1e9) are clamped.

**Proof ladder.** A measurement alone can never reach `your_pick`. No label
contains the word "verified". Unknown levels do not crash.

**Plan digests.** Block, param and kind changes all change the digest. Adding,
removing, duplicating or reordering actions invalidates a reviewed plan. The
revision store is bounded and evicts oldest-first.

### IRCommand, `tests/test_edge_cases.py` (40 tests)

Curve distance symmetry and the mismatched-length trap. Axis parsing:
whole-word matching so "darkroom" does not trigger `dark`, phrases beating the
single words inside them, deterministic resolution of contradictions. Matcher
degradation with a corrupt or key-less features file, unknown reference paths,
and unknown blend paths. Analysis on silent, single-impulse, two-sample and DC
input, asserting every feature finite. Blend symmetry, self-blend (must gain and
never cancel), and unequal lengths. Conversion boundaries: fade longer than the
IR, trim to one sample, trim to zero, empty resample, all-zero normalise,
unsupported bit depth. Pack-demotion boundaries in both directions.

---

## 4. Verification that is not a unit test

Some claims were checked against the real library and real hardware, because a
unit test cannot establish them.

- **Conversion fidelity.** Converting a real 200 ms capture to the 2048-sample
  FM9 profile retained **100% of source energy** with **0.00 dB mean and 0.00 dB
  max deviation** across 80 Hz to 6 kHz.
- **The analysis measures what it claims.** Spectral centroids ordered exactly
  as the capture names claim: a pack's "Bri" variant at 1155 Hz, its "Dar"
  variant at 870 Hz, the Soldano at 781 Hz.
- **Blend alignment is real.** Soldano plus a bright Marshall capture:
  -3.95 dB with 44.7% of the band cancelling naive, **+1.41 dB with 7.3%**
  after a 9-sample (0.19 ms) shift.
- **Classification cleanup.** 57 records left the cab pool and every one was
  inspected by hand: metronome clicks, 20-second recordings, drum samples. Zero
  legitimate cabs excluded.
- **Hardware.** The user-cab selection fix was proven on a real FM9: selecting a
  user IR into preset 16 channel C read back as `{bank: 2, ordinal: 26}`.

---

## 5. Known-open and self-inflicted, stated plainly

### 5.1 A phantom bug I filed, then disproved (issue #64, closed invalid)

An earlier version of this report claimed the suite was order-dependent:

    pytest tests/ -q -p no:randomly   ->  green
    pytest tests/ -q                  ->  6 failed

I filed #64 blaming cross-file state leakage. **That was wrong, and the
reasoning behind it was hollow.**

The six victims are all SOURCE-INSPECTION tests: they call
`inspect.getsource(...)` on a server function, or read `SCRIPT` parsed from
`ui/index.html` at import. The real error proves it:

    src = inspect.getsource(server._plan_for)
    assert "ToneCommand will lay a " in src
    -> got the source of _plan_counting, a different function

`inspect.getsource` uses the line numbers recorded when the module was imported
against the file as it exists at call time. **I was editing `server.py` and
`ui/index.html` throughout those seven-minute runs**, so an edit landing
mid-run made it slice the wrong function. Random ordering only changed whether
a given test executed before or after my edit.

The tell I ignored: run 2 passed 1329 while run 1 failed 6, with no relevant
code difference. That was a race against my own keystrokes, not a seed.

Proven by running the full suite in random order while touching nothing:

    pytest tests/ -q   ->  1329 passed

The three "ruled it out as mine" checks in the earlier draft were worthless.
All three ran while I was idle, so they only established that the failure does
not occur when nobody is typing. I read that as proof of innocence.

Two lessons, kept because they are the useful part:

- **Never edit source while a suite is running.** Any codebase with
  source-inspection tests will produce nonsense, and the nonsense looks like a
  real bug in someone else's code.
- A green obtained by not touching anything is not evidence an earlier red was
  spurious. It is the same experiment with a variable silently removed.

`-p no:randomly` is NOT required. Both orderings are green.

### 5.2 Issue #56 cannot be closed by testing

The FM9 USB re-amp routing spike needs the physical rig: real USB audio, a
global input routing change, and proof that routing restores after success,
error, cancel, disconnect and process restart. No amount of code closes it, and
marking it done would be the false certainty the other work exists to prevent.

---

## 6. Reproducing

    # ToneCommand
    cd fm9-tone
    python3 -m pytest tests/ -q                       # full, ~7m40s
    python3 -m pytest tests/test_edge_cases.py -q     # adversarial only

    # IRCommand
    cd ir-command
    python3 -m pytest tests/ -q                       # ~4s
    # analyze/blend tests need numpy; they skip cleanly without it

Both orderings are green; no flags are needed. **Do not edit source files while
a run is in progress**: several suites assert on `inspect.getsource` and on the
UI script text, and an edit mid-run makes them read the wrong lines. That
produced six convincing false failures and one wrongly filed issue (5.1).

---

## 7. Honest assessment

The adversarial pass was worth more than the feature work it audited. Four of
the six defects were in code written and committed the same day, and two of
them (2.2 and 2.3) defeated the purpose of the very features they lived in
while their own tests passed.

The pattern is consistent: the original tests confirmed the happy path the
implementation was written for. The defects lived at boundaries nobody had
asked about, and were found by probing ranges rather than asserting examples.
The pack-demotion bug in particular was found by printing the boundary across
pack sizes, not by a failing case.

Test count is not the useful metric here. Six real defects found, four of them
self-inflicted the same day, is.
