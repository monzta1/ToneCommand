# Axe-Fx III reference and NAM workspace, 2026-10-08

Historical pre-installer workspace record. The 2026-10-09 source port adds
separately confirmed native NAM installation for the exact measured Windows/
MK2/FW33 profile only; see [current bounds](FW33-COMPATIBILITY.md) and
[maintenance gates](AFX3-UPSTREAM-MAINTENANCE.md). Older search-only limitations
below remain historical, not claims about the new candidate's installer.

## Implemented offline

`/axefx3` now loads the exact FM9 stylesheet through `/axefx3.css` rather than
maintaining a copied theme. The hardware header, workflow rail, context area,
workspace, right rail and footer follow the FM9 layout. Request, Plan, Review,
Confirm and Send are separate screens, with back navigation, preserved drafts
and independent target/mute consent. Device choice and MK1/MK2 are retained;
cab import and NAM search are collapsible right-side widgets. This is still a
bounded workspace, not the entire FM9 chat workflow or interactive block
inspector. The route display reflects read state only. The actual FM9 executor
stays blocked for Axe-Fx III; stylesheet reuse does not change write gates.

The explicit MK selection is user-declared, not independently identified from
the hardware. On the only verified old firmware, 32.06, both user cab banks
remain available. On other firmware MK1 reserves User2 for NAM; an unknown
variant also blocks User2 conservatively. MK2 retains User2 metadata with
separate NAM storage. Changing to MK1 removes imported User2 names and
invalidates a pending tone review. Neither choice adds writable parameters.

The existing importer remains a connection-local **name catalogue**, not an
IR installer. Its captured ranges remain Factory 1/2 1-1024 and User 1/2
1-512. Actual device capacity is not inferred from this conservative range.
No cab/NAM/store whitelist was expanded.

One audio link can be included directly in the request. The browser downloads
through a bounded backend route, decodes locally, and measures the first
60 seconds at most. A local file is also accepted. Measurements include RMS,
peak, crest and sampled spectrum. This is a simple feature-based approximation,
not isolated guitar, direct AI listening, detected song sections, delay timing
measurement, or a proven sound match. Failed fetch/decode/silence stops the
proposal rather than continuing as though audio was heard. New Design clears
the audio selection and measurements without changing the device.

HTTPS only, 40 MiB, no playlist or DRM bypass. Hosted services use optional
yt-dlp. Direct URLs and redirects reject private addresses; the direct TLS
connection pins a checked public address with hostname certificate validation
to avoid DNS rebinding. No bearer credential accompanies audio fetches.

TONE3000 search reuses the user's existing OAuth/secret credential. API calls
use `format=nam&architecture=2`, or `format=ir` without a NAM filter. One page,
eight results, no rate-limit retries. The API's best-match order is preserved;
it is not acoustic ranking. Candidates are metadata, never instructions or
proof of original gear. An optional search term can accompany planning; an
authentication/API failure is shown instead of invented captures. Current
OAuth registration uses the primary loopback port 8909; a second-port preview
must not be mistaken for a working live sign-in installation.

## Still required before release

1. Verify FW33 identity/reply fields and native read layouts against Axe-Edit.
2. Capture NAM block IDs, insertion/routing, capture selectors, A2 compatibility,
   level behavior and readback. Do not substitute FM9 frames or unpin 32.06.
3. Implement entitled model download/validation and reviewed NAM installation
   within existing approved slots, then block placement with independent readback.
4. Add AI-driven capture choice, amp-only versus amp-cab routing and full
   main-page conversation/inspector parity. Search availability is not this step.
5. Perform muted hardware tests on a newly approved test preset and then safe
   user audition. No hardware write or live Tone3000/audio fetch occurred during
   this implementation's automated tests.

The owner's application on 8909 is unchanged. This work is in the integration
checkout, not deployed to that process. No PR was pushed or published.
An isolated simulator preview on port 8910 returned HTTP 200 for the page
and shared stylesheet, with disconnected device state. It was subsequently
stopped at the owner's request to use and maintain one TC installation.
Only the existing owner installation on port 8909 remains running. The
integration checkout is development work, not a second supported installation.
The upstream FM9 visual skin was subsequently applied directly to the owner's
existing `ui/index.html`, preserving its full existing chat and device handlers,
request widgets, wider inspector and send safeguards. This is a visual port,
not deployment of the bounded integration backend or its new MK/NAM APIs.
No backend/firmware gates or MIDI writes were changed. The owner server was
found stopped and its existing launcher restarted it; the main page returned
HTTP 200 with `FM9_MAIN_SKIN_1_5_4`. Only port 8909 is listening. Owner tests:
19 Python layout/offline tests and 60 JavaScript workflow tests passed; a real
Chrome visual check confirmed the hexagonal rail, five labels and no horizontal
page overflow at 1440 pixels. Further integration should preserve this sole
active installation's working features and local settings.

The subsequent layout port now gives the main 8909 application the former
preview's eight-scene row above the chain and compact 350px right rail. The
planner status and NEW DESIGN button share a top toolbar; Song/Audio and
original-request history remain separate native disclosures. AI settings and
manual/device controls are right-side disclosures; selecting a block opens its
original inspector automatically, including the larger EXPAND overlay. Review
filters occupy a row above the changes, rather than a separate left column.
The owner conversation, dynamic answer/build buttons, target/mute acknowledgments
and arm/send procedure remain in place. This does not claim deployment of new
MK/NAM backend functionality. Verification: 319 Python UI/chat/layout/safety
tests and 60 JavaScript workflow tests passed. Rendered controls fit at desktop
widths 1180/1280/1440/1920, with no duplicate DOM IDs or page overflow. Main page
serves `FM9_SHARED_LAYOUT_8909`; only 8909 remains active. No hardware write,
real AI request or preset store was part of these checks.

## Sources

- [TONE3000 API](https://www.tone3000.com/api): OAuth, A2 architecture filters,
  search rate limits and entitled model downloads.
- [Fractal FW33 beta 2 release bundle](https://www.fractalaudio.com/downloads/firmware-presets/axe-fx-3/33p0/axefxiii_dsp_rel_33p00_beta2.zip):
  embedded release notes describe MK1 User2 replacement and MK2 separate memory.

## Verification

Chrome tests run against the actual shipped HTML/JS with mocked APIs, including
new-design reset, MK selection, XSS-safe capture links and a generated 440 Hz WAV
fetched from a link in the request. This does not prove a hosted-service download
or a hardware write. Python tests cover storage policies, atomic cab imports,
credential non-disclosure, forbidden URLs, reference context, stale reviews and
the invariant capability-gate request table.

Recorded runs on 2026-10-08: all AFX3 Python suites, 697 passed in 14.82 s;
reference/text/controller plus mandatory safety suites, 188 passed in 221.76 s
(overlapping test sets, do not add these as unique tests). Actual Chrome
`tests/axefx3_ui.browser.cjs` and `node --check ui/axefx3.js` passed. Optional
yt-dlp 2026.8.19 was installed only in the integration virtual environment.

The shared-layout follow-up passed the actual Chrome five-screen workflow,
desktop fit at 1180/1280/1440 pixels, narrow-window guard, retained drafts,
consent invalidation and successful/failed mocked sends. The current reference
and controller suites passed 62 tests in 2.34 s. The mandatory safety suites
plus reference/controller suites passed 115 tests in 220.11 s before the last
stylesheet-equality test was added; the subsequent 62-test run covers it.
These sets overlap. Browser tests use mocked APIs and do not write hardware.
