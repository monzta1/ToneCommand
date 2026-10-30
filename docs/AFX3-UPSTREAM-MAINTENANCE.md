# Axe-Fx III maintenance and publication

## Decision and current state (2026-10-09)

Maintain this as an upstream-compatible device contribution, not a separately
copied FM9 application or an Axe-Edit-dependent addon. The intended architecture
is upstream's shared planner/UI plus `devices/axefx3`, with explicit per-firmware
capabilities. The integration branch includes upstream 1.5.14 and moves the
bounded FW33/NAM protocol, installer, account and design path to
`devices/axefx3`. The original owner checkout is preserved; the single active
runtime uses the hardware-tested integration checkout. This is NOT a one-click update:
shared interfaces still require regression and hardware changes need review.

There is one user installation, on port 8909. Integration checkouts are source
workspaces, not additional supported/running instances. Never copy account
settings, cab lists, model weights or user presets into a public development
branch. Preserve the successful 2026-10-08 preset test as a hardware baseline;
its audible acceptance was reported by the owner on 2026-10-09. That does not
certify untested firmware, controllers, NAM formats or upstream features.

## Repeatable update check

### Current source reconciliation, 2026-10-30

The maintained foundation is7c6b59f, including the maintainer's merged289/290
and shared security fix292. The full FX3 adapter/protocol and historical
evidence stay separate from upstream's mapped read-only interface. Global
local-only checks run outside all fork workspace redirects; Gig Lock remains
reachable and settles in-flight workspace writes under the same host lock.
The combined runtime passed7,323 tests/19 skips; final per-head installation
and remote CI must be recorded separately from those local results.

The next independent draft294 ports only the separately pinned Beta5
model0/A Gain/Mid experiment. Draft295 fixes a test-fixture cache leak and
does not change production caching. No new release, hardware promotion,
package or automatic upstream approval follows from preparing either draft.
The physical unit is not needed for this source work; native CAB acceptance
and the exact upstream experiment's native regression remain later gates.

### Historical source reconciliation, 2026-10-28

The candidate foundation is upstream1.6.2 at
`4d81851ecd163a984fd5dc3fc2cff9ad7a0f0dde`. Keep the older dated notes below
as historical evidence, not current feature limits. The integration manifest
records source reconciliation separately from final regression, installation,
native hardware and remote CI acceptance. No firmware write is enabled by a
version bump or a successful merge.

The official read-only III source maps to `readonly_adapter.py` and
`readonly_protocol.py` in this full fork. Its closed name/Amp components and
unchanged-assertion tests use that explicit namespace. The existing full
`adapter.py` and `protocol.py` retain their measured workspace boundary. For a
future upstream update, compare these two mapped files with their original
upstream paths, then review connection handoff and shared snapshot dispatch.
Never resolve an add/add conflict by replacing the full adapter with read-only
source, or by letting the shared executor use the full workspace adapter.

The shared Devices selection and declared chassis capacity use the official
read-only interface. The existing explicit workspace Connect transfers MIDI
ownership only after closing that interface. Generic FM9 execution remains
blocked in the full workspace. Problem reports now work without JavaScript
and link to this fork's tracker without querying the unit. The fork remains
Unofficial; original authorship and legal attribution are retained.

This preparation is not an extra maintained application or a deployment. The
two focused draft contributions289/290 are not merged, rewritten or approved
by reconciling this branch. Their upstream review remains separate.

### Current source integration boundary, 2026-10-21

The shared source integrates upstream1.5.16 at
`2aa7a3998b2cec59edff8cd7e0f3f30d2571ebe9`. Reconciliation preserves upstream
USB discovery, DDLP profiles, watcher startup ordering, four-cable/multiple-rig
reading, version badge and bottom-shelf layout, alongside the existing FX3
selection, planner seams, controller workspace and separate CI/browser gate.
Learned device profiles and private NAM/account files remain excluded from
publication. The FM9 never-brick `_send` guard is not changed. The maintenance
manifest uses this upstream foundation rather than reporting integrated work
as missing. This is source integration, not new device-write or audible acceptance.

[Draft PR270](https://github.com/monzta1/ToneCommand/pull/270) remains a review
contribution, not an upstream merge. The existing Unofficial1.5.15-fx3.1 release
and tag remain pinned to their original99adce1 source snapshot; neither is
silently replaced by this reconciliation. No live application restart, preset
change or new hardware test is required to resolve Git conflicts. Remote CI,
clean installation and physical FX3/FM9 acceptance remain separate checks.

Upstream's shared Python3.14/supriya acceptance applies to its measured FM9
path, not automatically to FX3. Native FW33 writes are pinned to the measured
Windows/Python3.12/mido combination. Other runtimes may inspect read-only state;
they receive an explicit unsupported-write-profile message. Scripted test ports
do not establish native acceptance. Do not relax this gate from metadata alone.

The earlier dated sections below record historical limits. The current released
measured CAB scope is2048 Factory names, complete imported User1/2 addressing,
four-IR mixing and separately restricted FullRes metadata. The entire MK1 User2
bank is reserved for NAM; MK2 has separate NAM memory. See
[AFX3-CAB-INVENTORY.md](AFX3-CAB-INVENTORY.md) for hardware acceptance.

Successful eight-scene design metadata and imported CAB names now persist in
the private owner state directory, never in Git. Explicit cold-runtime resume
requires new consent and complete eight-scene readback. Source checkout clean
installation and resource/API smoke have run in a fresh same-Windows environment;
this is not other-machine/platform or remote CI acceptance. See
[AFX3-DESIGN-HISTORY.md](AFX3-DESIGN-HISTORY.md).

Released T808 Mod, Modern VCA and10 Band Variable Q voices stay within the
adapter. Each passed actual selected-AI/normal SEND and independent editor
acceptance; their selectors do not enable numeric voicing for other models.
One-to-eight scene prefixes are released on the same measured route, with
four stored Amp/Cab voices, not eight independent channels. These changes do
not extend the shared FM9 planner, transport or never-brick guard. Add their
tests and runtime/data hashes to upstream reconciliation. Unmeasured prototypes
must not be released based on simulator success. The complete seventeen-item
status lives in
[AFX3-COMPLETION-BACKLOG.md](AFX3-COMPLETION-BACKLOG.md).

### Scene-intent contribution boundary, 2026-10-16

General scene-goal checks and listening-feedback preservation live in
`devices/axefx3/scene_intent.py`, the device design compilers and device review
service. They use upstream's selected planner; they do not fork `fm9/planner.py`,
the FM9 executor or its transport/never-brick guard. The existing FX3 plan
endpoint gains optional refinement context, not a second application or MIDI
owner. See [AFX3-SCENE-INTENT.md](AFX3-SCENE-INTENT.md) for musical versus
hardware guarantees, limits and the connection-local baseline requirement.

When updating upstream, run the mandatory contract/capability/UI-warning tests,
scene-intent, album/serial/NAM/text/eight-scene/review tests and the actual Chrome
workflow. Musical prose or goal validation does not promote firmware, model,
IR-bank, controller or effect-parameter evidence. New setters still need the
hardware ladder in the local KB, with private evidence excluded from the PR.

### One Windows runtime and startup verification, 2026-10-12

From the maintained integration checkout, use:

```powershell
.\tools\start_tonecommand.ps1
```

This opens Chrome at8909/axefx3 and starts/reuses only this checkout. It checks
the running source root, real listener PID and startup-pinned FX3/shared-core/
UI hashes. An old owner checkout, occupied8910, another app or changed imported
code is refused, not killed or silently reused. No8909-to8910 fallback exists.
Restart a stale instance normally before running the launcher again. The GUI
footer shows the FX3 revision; its tooltip identifies the source root and PID.
The connected root URL also opens the tone workspace, not a legacy planner.

Private settings can stay in their existing directory:

```powershell
.\tools\start_tonecommand.ps1 -SettingsDirectory 'C:\YourExistingTCSettings'
```

The directory must contain existing ai_settings.json and store_slots.json;
user_cabs.json is optional. Nothing is copied into Git or added to a slot
allowlist. Optional -Connect -AxeFxVariant mk2 explicitly opens a read-only
connection and sets the locally declared profile; it does not prove chassis
identity, mute audio or send any preset action. With an already matching
connection it preserves pending reviews instead of redundantly resetting
the profile. Axe-Edit must be closed normally first. -NoBrowser is supported.

FW33 album mode still uses the measured Factory2 IR1 selections only. Uploaded
User names are metadata, not selector calibration. Explicit User-cab intent
is refused before AI, without silently replacing it by Factory. A User3 export
is outside this FX3 catalogue and is rejected atomically with the exact bank/
slot; do not trim or remap it without an explicit bank/source decision. Native
User-bank acceptance requires a separate independent muted measurement.

Actual GUI acceptance on2026-10-12 uses the configured real AI, EXPLORE ROUTES,
manual AMP/CAB selection and GENERATE PLAN on empty322/scene1. It produces
AI-Metallica albums, eight named album lead/solo scenes, A,A,B,B,C,C,D,D and275
reviewable actions. The complete public before/after state is unchanged apart
from two explicitly synthetic import-test name labels. SEND, Store, navigation
and installer requests are forbidden in this browser test. Temporary labels
are cleared by a normal disconnect/reconnect afterward. This is plan formation
from the GUI, not new hardware-write acceptance or an audible assessment.
Final mandatory contract/capability/UI-warning and changed simulator suites
pass399 tests in122.69s, four workers. Actual mocked-API Chrome also covers
the revision/source footer, cab-selection warning and retained legacy workflows.

The owner desktop launcher had pointed to the preserved legacy checkout; the
running server consequently sent the AI the obsolete NAM-only FW33 reference.
Its replacement delegates to this maintained launcher while referencing the
same private AI/Store settings. The legacy checkout is not rewritten or used
as a server. Exact source identity matters more than browser refresh alone.

Next User-bank gate: with freshly confirmed external mute, use an authorized
test preset distinct from the stored reference and the independently verified
Legacy IR1-only foundation. Record Axe-Edit's changed bank/slot selectors,
including User1/User2 boundaries and exact-zero behavior, then correlate the
visible names/slots with complete native Cab words. Only afterward implement
bounded native replay with whole-state preservation and a fresh independent
editor comparison. Imported labels never replace that measurement, and IR
memory installation/mixer/pan writes remain separate permissions/capabilities.

### Roadmap reconciliation, 2026-10-09

There is no standalone ROADMAP file in the inspected upstream main tree.
Follow the live [milestones](https://github.com/monzta1/ToneCommand/milestones)
and issues, rather than a copied feature checklist:

| Upstream work | FX3 relationship | Next gate |
| --- | --- | --- |
| [NAM epic I](https://github.com/monzta1/ToneCommand/issues/140), especially install #147 | Native measured MK2/FW33 install and slot001-256 inventory already implemented; do not rebuild the installer | Nonzero player selection now captured/replayed at250/256; zero-selector change remains blocked |
| Capture placement #148 | Exact NAM route, quiet voicing, scene A/B and explicit installed-slot selection accepted | No speculative001 zero selector, routing splice or new firmware profile |
| Inventory/usage/removal #151 | Inventory exists; preset reference indexing and protected deletion do not | Do not describe inventory as complete usage/removal support |
| [Rig Reconstruction](https://github.com/monzta1/ToneCommand/issues/224), #225-230 | Shared source/graph reader, bounded FX3 reports and actual pasted-rig hardware build accepted | Live YouTube source regression and physical audition remain separate |
| Parallel/stereo #16 and four-cable #244 | Neither automatically enabled on FX3 | Disclose closest-mode simplification; faithful mode refuses unsupported geometry |
| Source/build defects #243, #245-248 | Rack effects must not become delay by default; multiple rigs and unsupported insertion must not silently merge | Bounded mapping, source-order checks and existing complete route preflight |

Upstream main3f20af0 contains six newer commits than the integrated c2dae138
foundation. Their transport/CI and dead-scene comparison changes are not a new
music-only audio reconstruction engine. Audit them by the existing update
checker; do not infer FM9/macOS transport evidence enables FX3/Windows writes.

The source extension distinguishes an explained equipment/video source from
a measured sound reference. It uses the user's single selected text provider,
preserves graph provenance and provides closest/faithful/simplified FX3 reports
through the existing review/send boundary. This is not isolated guitar audio,
an exact sound clone, automatic download/install/Store or a new hardware profile.
Source tests and mocked browser passes are not hardware or auditory acceptance.

Earlier selector checkpoint: the runtime built test328 using the accepted NAM001 path
with40/40 verified actions, no Store. An attempted exclusive editor handoff was
rejected by the execution environment before it ran. The runtime stayed on328;
no editor capture, non001 selector, new NAM install or firmware capability was
claimed at that point. Later user-operated editor capture and independent TC
replay resolve nonzero selection; the rejected composite operation was not retried.

Validation for the source extension:830focused source/NAM/shared-gate tests
passed, then277mandatory/changed/maintenance/packaging tests passed after the
final changes. Real Chrome exercises source choice, source-report escaping,
consent invalidation and compatibility with an older backend. One real
configured Codex extraction passed. A wheel was built; these results do not
claim remote CI, a deployed new Python handler, a live YouTube extraction,
source-driven hardware execution or NAM selector acceptance at that checkpoint.

Later acceptance: user-operated editor capture250 ->256 ->250, exclusive TC
selector replay, actual configured-provider41/60-action builds on329 (including
pasted explained-rig source), and separate Store/reload succeed. Current runtime
on8909 loads the new source and selector handler; actual headless Chrome checks
occupied choices001/250/256 and current256 without any writes. Full regression
4404passed/16skipped, then567mandatory/changed checks after final small guards,
and mocked/actual-runtime browser passes are local evidence, not remote CI.
NAM001 zero-selector change, live video ingestion and physical sound remain
pending. See `FW33-COMPATIBILITY.md` for the exact per-operation scope.

For a fresh source checkout without a local KB, first run:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/bootstrap_fx3_kb.py
```

This creates only gitignored `kb/` from the public compatibility/maintenance
facts. It does not reproduce upstream's private knowledge, overwrite an existing
KB, access an account or authorize hardware. Preserve and reconcile an existing
KB manually. Private owner evidence can remain local; distributable facts belong
in the reviewed public docs so another maintainer can bootstrap safely.

From the owner checkout, with the device off:

```powershell
.\Check-ToneCommand-Upstream.ps1
.\Check-ToneCommand-Upstream.ps1 -Fetch
.\Check-ToneCommand-Upstream.ps1 -Json
```

The default is offline. Fetch validates the upstream URL and refreshes Git
objects only. Neither command merges, restarts TC, changes settings, calls AI,
opens MIDI, installs NAM data or writes a preset. The JSON report can be used
by later automation. `config/axefx3_upstream.json` records the audited commit,
the existing integration foundation and ordered ownership/review rules.
An audited version is deliberately NOT labelled integrated or hardware-tested.
The report checks whether the declared foundation is actually in this checkout's
HEAD history; a missing ancestor is a warning, not a passed integration gate.
Unclassified files need review. Local overlaps flag potential reconciliation,
not an exhaustive list of merge conflicts or proof of feature equivalence.

## Branch and release workflow

1. Keep `main` as a clean upstream mirror in the fork. Keep a stable `axefx3`
   release branch and develop each update on an `integration/axefx3-*` branch.
   Use a checkpoint branch/tag before migrating. Do not reset existing work or
   force-push to obtain this layout. The current preparation branch is local.
2. Fetch upstream and inspect changes from the known integration foundation.
   Resolve common planner/UI changes separately from device-specific protocols.
   Keep FW33/TONE3000/NAM behavior in the isolated FX3 adapter before deploying
   the newer foundation. Do not replace it with the FM9 path. The local KB is
   newly built from this fork's evidence, not the upstream author's private KB.
3. Run simulator, parser, validation, browser and package tests. Keep Windows
   and Linux CI required. Unknown hardware behavior must remain blocked even
   if the simulator accepts it. A CI definition is not a remotely passed run.
4. With separately confirmed power/mute/target permissions, verify the integrated
   application on allowed test presets, including readback and stored reload.
   New persistent NAM writes need their own authorization. Do not widen any
   preset/CAB/NAM whitelist. Human listening and physical controllers remain
   separate acceptance checks; there is no physical audio limiter.
5. Review the public diff and licensing, run the release audit, then request
   publication approval. Push a feature branch to the owner's fork and open a
   draft PR to `monzta1/ToneCommand:main`. Small dependency-ordered PRs are easier
   to review than the full legacy fork. Never push directly to upstream main.
6. After accepted CI/hardware evidence, tag a tested source release. Retain
   firmware bounds and caveats in release notes. Do not advertise an installed
   wheel/frozen app until its resources and GUI have passed installed tests.
   If upstream merges the adapter, prefer upstream releases over maintaining
   another permanent UI fork.

## Publication hygiene

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/release_audit.py --staged
.\.venv\Scripts\python.exe -X utf8 tools/release_audit.py --ref HEAD
```

These scan Git blobs, not ignored account files. The index scan includes new
staged files; the committed scan is independent of working-tree edits. Reports
contain paths/rules, never suspected credential values. It blocks known private
artifacts and high-confidence token patterns. It is not an exhaustive secret
scanner or history audit; publication also requires GitHub secret scanning,
review of any previously pushed history and a manual third-party license review.
No NAM weights, private hardware captures or third-party guide prose belong
in the PR. Synthetic test data and facts-only metadata may be distributed only
under their applicable licenses. Do not commit local one-off hardware scripts
as reusable product features without first removing owner-specific assumptions.

## Acceptance gates and remaining work

- Gate A: successful live implementation checkpoint and offline regression.
- Gate B: maintenance tools, release tripwire and cross-platform CI preparation.
- Gate C: latest upstream integrated with isolated FX3 FW33/NAM support; full
  application regression, real mocked-API Chrome workflow and module packaging.
  Source-checkout distribution only; installed wheel GUI is not advertised.
- Gate D: muted hardware regression of that integrated build plus user audition.
- Gate E: public diff/licensing/history review, actual GitHub CI, draft PR.

The existing integration worktree requires a private `kb/` by its AGENTS.md.
It was absent. On 2026-10-09 the owner first requested waiting, then explicitly
authorized building the missing local knowledge base and completing FW33/NAM
adapter integration. Populate it only from inspected sources and recorded
evidence, clearly separating legacy hardware acceptance from new code testing.
No upstream planner change was applied to the working owner installation.
Provide `kb/INDEX.md`, `kb/index.json`, the referenced `always_load` resources
and task-relevant files under the integration checkout. Hardware work additionally
requires `kb/HARDWARE_RULES.md`. Keep the knowledge base local and gitignored;
never publish account credentials or private captures to make this available.

Working source checkpoint: `939e3ef8cab2a64c7ce043c213314b9ebe02539a`, branch
`checkpoint/axefx3-fw33-nam-20261009`. Before any maintenance-code change its
full offline suite passed 2,939 tests, with one skip and four existing Starlette
warnings. Maintenance preparation subsequently passed 2,958 tests and one
skip, with the same warnings. The simulator preset doctor passed all three
checks; listening remains pending for simulated presets. The shipped
JavaScript suites passed 61 and 13 tests. These results
belong to the current working implementation, not the newer integration backend.

Latest audited source: [upstream 1.5.14 changelog](https://github.com/monzta1/ToneCommand/blob/c2dae138272cbfb26096ff7d92e643eacf8c32ab/CHANGELOG.md).
Device evidence and exact bounds: [FW33 compatibility](FW33-COMPATIBILITY.md).

## Proposed review order

Prefer dependency-ordered PRs: independent adapter/discovery and firmware bounds;
FW32.06 review/executor and controller UI; FW33 exact profile/native NAM/account;
then shared reset/UI and maintenance improvements that upstream wants. Keep the
integration branch as the complete tested candidate, not a second live server.
No draft PR, branch protection changes, push or release happened during this
offline preparation. Confirm repository visibility and publication permission
before any remote write. The local raw hardware evidence and account/model
files remain private; public claims must be supportable from reviewed facts.

## Offline candidate evidence, 2026-10-09

- Windows/Python3.12: final full SIM suite **4,022 passed, 16 skipped**, 349.45s,
  eight workers. Mandatory device/capability/UI-warning plus maintenance/NAM
  review/installer gates **126 passed**, 246.72s, four workers.
- Real headless Chrome with shipped HTML/JS and mocked APIs: common layout,
  request retention/reset, review/send consent, text safety and native NAM
  preview/install/one-scene-foundation/two-scenes/separate-Store workflow pass.
  The chain browser test and five shipped reset behavior tests also pass.
- SIM doctor: path, scenes and levels **3/3**, audible result always pending.
- Source wheel built; eleven new adapter/catalog entries verified in its actual
  archive. This is a module packaging check, not an installed/frozen GUI claim.
- Public Git index/tree tripwire passes; no known private account/model/preset
  artifacts. Manual license review, full history security review, actual GitHub
  CI, new muted adapter hardware acceptance and deployment remain open gates.

The device stayed off. No real AI request, NAM install, preset write/Store,
Axe-Edit automation, owner-app restart, remote push or PR creation occurred.

## Subsequent muted hardware evidence, 2026-10-09

The preceding paragraph applies to the offline phase only. The owner later
confirmed power on, external audio off, and explicitly authorized test presets
321-329 including replacement. Candidate `4cc5834` was then tested on declared
MK2 hardware with independently identified `33.00-beta.20261006` firmware.
This is a narrow acceptance result, not general FM9/FX3 feature parity.

- Real configured Codex backend, no substituted AI response or fallback:
  an empty preset327 foundation executes all **40 actions**; a subsequent
  existing-route design executes all **58 actions** for Rhythm/Lead with NAM A/B.
  The actual registered review/send API and live adapter were used via ASGI.
  Every action passes its independent readback, with no remaining skipped actions.
- Separate same-slot Store through the actual API succeeds under the owner's
  already-existing321-329 policy file. After selecting empty328 and returning
  to327, complete block bulks, grid, modifiers, scene names and NAM hash match
  the pre-Store state. The diagnostic bank/PC helper is not a newly enabled
  adapter reload feature; generic preset reload remains deliberately disabled.
- Additional live scene checks and independent Axe-Edit show NAM A/B with
  distinct EQ/levels, the requested per-scene bypass states and shared effect
  timings/mixes/levels. Axe-Edit is opened only after TC releases MIDI and is
  closed gracefully afterwards. It is not used to build or save the preset.
- Empty two-scene requests are refused before the AI call. Unsupported block
  deletion/model selection, feedback95%, Output+12dB and adding a NAM block to
  the occupied route are refused before writes. Complete state stays unchanged.
  No claim is made that FW33 can clear, splice or replace an existing route.
- Stored reference326 retains its complete grid, parameter bulks, modifiers
  and scene names. Native NAM memory reads return all65536bytes with the same
  hash throughout. No NAM installation, capture replacement, global MIDI map,
  firmware, driver or allowlist change is performed.
- The new account service reads the existing encrypted login and downloads the
  selected entitled capture through the actual TONE3000 API. Installation
  preview on empty328 compiles to the exact currently installed payload hash.
  Each of the three missing-consent cases refuses commit; complete device/NAM
  state stays unchanged. This proves preview/consent handling, NOT installation.
- Post-hardware mandatory device/capability/UI-warning, maintenance and FW33/NAM
  workflow regression: **127 passed**, 114.88s, four workers. Public Git tree
  tripwire passes; it is not a complete history/license/security audit.

Preset327 is stored as `AI-FX3 Integration Test`. It is a transport/scene test,
not a claim of a complete cab voicing, matched recording or safe physical
loudness. Cab is intentionally bypassed. External audio remains off. Physical
audition/controller checks, the new native installer's hardware WRITE pass,
manual licensing/history review and actual remote CI remain separate gates.
Local raw reports and owner-specific harnesses are private and gitignored.
No owner-app replacement, remote push or PR publication occurred.

## NAM slot-selection acceptance, 2026-10-09

The owner subsequently authorized autonomous NAM250-256 tests and requested
product support for destinations001-256 with occupancy and explicit choice.
The updated candidate adds a serial256-name inventory, first-free suggestion,
destination selector and slot-bound preview/consent. Existing FM9 traffic guards
and configured allowlists are unchanged. Full-bank and failed-read paths do not
silently select a replacement. Native installation is not preset selection;
the FW33 preset builder still required NAM001 at that checkpoint. The later
NAM player-selection acceptance in `FW33-COMPATIBILITY.md` supersedes that
restriction, including the later independently measured001 zero selector. It includes native
250/256 selector replay, real configured-provider41/60-action builds on329,
shared explained-rig text extraction and separate same-slot Store/reload.

- Axe-Edit name GETs independently establish all256 addresses. Read-only
  exports establish memory headers/GETs at250/256; erased slots contain a full
  65536-byte all-FF image. Empty/populated preset reply context differs and is
  not a slot ordinal. Selected slots require complete export verification.
- Actual TONE3000 download and registered TC API commit install the supported
  selected capture in250 and256, without Axe-Edit as installer. Each receives
  full65536-byte hash/name/address readback and a verified private pre-write
  recovery export. Missing target consent refuses before writing. A subsequent
  inventory reports both occupied; a repeat preview recognizes occupancy.
- Independent Axe-Edit NAM manager shows the same capture in250/256. No editor
  import, rename or Save is used. NAM001 and complete stored reference326 remain
  unchanged; test preset328 is still empty and unsaved, as before installation.
- Real Chrome with mocked APIs passes first-free/manual choice, occupied-slot
  warning, changed-slot and refresh invalidation, all-full/manual replacement
  and incomplete-inventory refusal. Offline full suite: **4,304 passed,
  16 skipped**,327.88s,eight workers; subsequent changed NAM/account/maintenance
  suite **392 passed**,32.46s,four workers. Mandatory gates **54 passed**;
  final mandatory plus changed-module regression **564 passed**,233.17s.
- Single local runtime on8909, using existing owner settings and policy files:
  real Chrome, actual account and live MIDI verify all256 destination options,
  first-free002, occupied250/256 and a read-only occupied250 preview. Missing
  confirmations keep install disabled; rescan invalidates the pending preview.
  No additional install, Store or AI request is triggered by this browser test.

Only250/256 were written during this acceptance; other addresses are validated
by captured name addresses, measured header encoding and synthetic tests, not
256 destructive hardware installations. Private scripts, screenshots, recovery
exports, account state and model weights remain untracked. Remote GitHub CI,
licensing/history review, audition and owner-checkout deployment remain separate.
The candidate is opened as the single local runtime for this feature; the old
owner checkout is retained intact, not overwritten or promoted to a new release.

## Subsequent YouTube and explicit-route regression, 2026-10-09

The later [FW33 compatibility evidence](FW33-COMPATIBILITY.md) records an actual
YouTube download/local measurement, configured-provider comparison of both
musical strategies, native long-name capture installation in252,41/60-action
GUI builds on325 and separate Store/full-state diagnostic reload. Stored326
and existing full NAM memories remain unchanged. No sound-match claim follows.
Read-only live exploration now finds catalog candidates with short artist/song
queries; the user still chooses route/capture/destination explicitly. Unknown
FW33 AMP/CAB/model/controller writes remain gated, even when musically advised.
The native installer and writer have no Axe-Edit runtime dependency.

The UI and read-only comparison are isolated in the FX3 package/workspace,
not a replacement FM9 planner or forked shared transport. Keep these tests in
the upstream-update gates: explicit choice/no implicit NAM, changed-source
audio invalidation, catalog failure/empty matches, normalized label with
unchanged weights, independent readback and reference-preset preservation.
The public-facts KB bootstrap reflects the measured player selector while
preserving an existing private KB. Product capability promotion still needs
its own exact-firmware measurement, not a simulator or upstream claim.

Only the single8909 integration runtime is used. Owner checkout/settings are
preserved; no remote push, PR, release, branch protection or allowlist change.
