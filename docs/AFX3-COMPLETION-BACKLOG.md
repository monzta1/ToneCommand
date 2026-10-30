# Axe-Fx III completion backlog

## Shared MK1/MK2 foundation, 2026-10-30

One central chassis definition supplies capacity to the shared read-only
protocol and full workspace; the parameter/protocol implementation is common.
Beta5 user-name imports now use modern bank addresses instead of falling back
to the old layout. MK1 protects NAM-reserved User2 and persistent FullRes,
including stale-cache and direct-selection paths. Private name caches are
isolated per build/chassis. See [the shared implementation](AFX3-SHARED-IMPLEMENTATION.md).
This is source integration, not new native MK1 or broad Beta5 write approval.
The operation-specific completion work below remains open where indicated.

## Current hardware continuation, 2026-10-30

After the offline checkpoint below, the owner freshly confirmed power and
external mute; the desktop was accessible. Exact MK2 Beta5 identity was read,
and327 was empty after restart. An isolated, unsaved fixture was built through
Axe-Edit without Input/Output/cables;326/328 were untouched.

PR294 runtime85d86beb passed four actual upstream registered native API SETs,
Gain5.0->4.6->5.0 and Mid5.0->5.6->5.0, each freshly reviewed. Separate
canonical processes compared full native state before/after; fresh editor
instances independently confirmed changed and restored values. Complete final
baseline matched. This is not a native browser SEND or whole-rig test.

Legacy CAB1/A Factory1 indices1/2 in all four IR slots passed eight exact
captured SETs, full-state preservation and fresh independent editor comparisons
before, changed and restored. No production CAB capability was enabled. See
[the family evidence](AFX3-BETA5-PARAMETER-FAMILIES.md). Full reports, captures
and screenshots remain private; no Store/NAM/IR/global/firmware write occurred.
Final327 contains disconnected Amp1/A bypassed at -12dB and active Cab1/A.

## Historical offline update, 2026-10-30

The maintainer merged289 and290 on28October. Their bounded shared bridge and
review/SEND wiring are accepted upstream; this is not general Beta5, MK1 or
whole-rig write approval. The retained firmware/operation gates stay intact.

Upstream292 at7c6b59f is reconciled into this fork: strict local Host/Origin
checks, settled Gig Lock and queued-write checks. The shared middleware runs
before our full-workspace redirects, and `/api/gig` remains reachable there.
Independent fake-workspace tests prove an in-flight controller SEND holds
the shared lock until completion and a later SEND refuses after Gig Lock.
The security checkpoint8425180 passed238 mandatory/changed tests and actual
temporary-loopback HTTP/Chrome acceptance in simulator mode, with no native IO.

The pending-download cache leak293 was reproduced in the reported file order
and isolated in the per-test fixture without changing production caching.
The combined runtime passed7,323 tests/19 skips and174 mandatory/related
checks; the one USB-enumeration warning is informational. Documentation and
foundation metadata are refreshed after that full runtime run. Exact final
commit installation and remote CI are separate checkpoints, not assumed here.

Two small upstream drafts remain independent of the full fork:

- [294: separate Beta5 Gain/Mid experiment](https://github.com/monzta1/ToneCommand/pull/294),
  existing model0/A only. The exact upstream port still needs its own native
  regression; the earlier77e2ded native evidence is reference, not relabelled.
- [295: per-test install-cache isolation](https://github.com/monzta1/ToneCommand/pull/295),
  three test/changelog files, no production behavior change. The reported
  serial order plus deterministic regression passed129 tests. All15 remote
  CI checks on5ebe039 passed. Local full4,004/17 retains the separately
  disclosed symlink-creation privilege failure, not a weakened security test.

No native port, Axe-Edit, Store, NAM/IR memory, global setting or firmware
operation was used for this update. Resume the independently recorded CAB
comparison only after fresh power, external-mute and desktop confirmation.

## Historical master plan and GitHub audit, 2026-10-28

### Shared reviewed-edit integration candidate

The prepared289/290 code is being reconciled into this fork, not merged into
upstream. Default connections stay read-only. The opt-in manual Gain/Mid
writer keeps its earlier exact MK2 pin and refuses Beta5. Namespace mapping,
source identity for its script, in-flight New Design protection, loopback
origin checks and bundled labels are included. Initial route/workflow checks
passed208 and expanded targeted checks264. Final mandatory/changed checks
passed342; the complete suite passed7,202 with19 skips and one informational
Windows USB-enumeration warning. Real Chrome mocked read-only, capacity and
reviewed-edit flows passed. The registered API was also tested on the native
Beta5 connection: default mode refused preparation without additional traffic,
and explicit opt-in refused the unmatched identity using GETs only. Full state
was unchanged. This is negative acceptance, not a successful Beta5 write.
The committed integration atb6d0303 has all16 remote CI checks green. A fresh
Windows CMD installation of that exact commit passed437 bootstrap tests/1
skip,171 installed checks,261 follow-up checks and all seven mocked Chrome
flows. These are same-host installation results, not another-machine, native
browser SEND or listening acceptance. Existing
completed source at e8daacb has all16 actual remote checks successful and a
fresh Windows CMD install:437 bootstrap/1 skip,171 installed,39 extra checks,
five browser flows. Its earlier full6,980/19 and later313 targeted results are
separate from this new integration candidate.

See [the explicit capability matrix](AFX3-CAPABILITY-MATRIX.md). H-W remain
operation-specific, and F/G upstream review is still external. A known
remaining UX constraint is the host's retained normal-plan revision cache:
it is not an active-plan lifecycle, so experimental preparation can remain
blocked after a normal plan. Do not clear authorization history to hide that
constraint; design a separately reviewed connection-bound invalidation flow.

### Later continuation: targeted Beta5 Amp measurements and CI repair

A subsequent separate candidate adds explicit Beta5 reviewed Gain/Mid for
existing model0 only, not a full-workspace profile. It has four native
registered-API SETs with fresh separate reviews and independent editor checks,
plus six captured native boundary literals with full preservation. Its final
software/CI/installation acceptance is separate from b6d0303. See
[the bounded experiment](AXEFX3-BETA5-REVIEWED-AMP.md). Other Beta5 families
and normal model selection/rig construction remain blocked.

The CI-repair source atd9a0704 passed the full6,980 tests/19 skips plus156
mandatory/targeted tests and the full mocked FX3 Chrome workflow. The later
capability correction also declines advertised renaming on unverified builds;
its targeted and per-head CI results must be recorded separately. No write
guard, firmware allowlist or memory policy is expanded.

The K model scan subsequently completed all336 editor selections after two
desktop interruptions. All336 independently captured selector literals were
then replayed through a separate private native probe. Fresh independent
queries, repeated full-state reads and preservation of other channels, grid,
modifiers, controller bulks and names passed at every step. Exactly336 native
model SETs were sent without retry; final model0 matched the complete baseline.
The quiet -12dB level and bypass state were preserved throughout. The final
fresh post-native editor comparison and another complete native comparison
subsequently passed after desktop access returned.
The earlier editor had closed normally without Save after a fresh fixture
check. No forced close, desktop-security workaround, Store or reference326/328
change occurred. Current327 is an unsaved, disconnected model0 Amp fixture,
not a tone preset. These measurements do not enable the normal Beta5 planner.

The H/I source checkpoint at7c0d2b6 passed6,980 tests/19 skips and379
mandatory/targeted checks on this Windows host. The one USB-enumeration
warning is informational. This is not a claim that remote CI is green.
The remote083e22 run exposed a full-browser test still targeting the removed
language dialog and Windows launcher tests with unavailable Get-FileHash.
These receive explicit native-dropdown and platform-SHA256 fixes, preserving
all draft, consent, stale-source, no-second-owner and fail-closed assertions.
Record the final local and per-head remote results before release acceptance.

J now additionally has sixteen exact native Amp literal SETs across eight
controls on isolated327/A, with full-state preservation, separate restoration
and fresh independent Axe-Edit checks. See
[the bounded family record](AFX3-BETA5-PARAMETER-FAMILIES.md). This is private
measurement evidence, not implementation of a normal Beta5 family writer.
The production adapter's before-output refusal remains correct and recorded.
Fresh access was confirmed; the earlier request for confirmation is historical.

### Later hardware continuation: read-only identification and names

Fresh power/external-mute/desktop confirmation was received after the source
checkpoint below. The full initial327 observation exactly matched the earlier
Amp/Pitch fixture; it was recorded before editor preparation reloaded that
disposable edit buffer. No Store or changes to reference326/328 were performed.

Independent Axe-Edit1.15.02 export/native comparison now covers all1024 MK2
name addresses, including every upper slot512..1023. Exact matches:1022 total,
511 upper. Two names differ only by an initial space omitted in the editor
export. Raw names remain unchanged and the checker reports the differences;
this is not a claim of1024 exact matches. Full post-scan state preservation
passed. See [the qualified read-only record](AXEFX3-READONLY.md).

Known full-response firmware labels now reach the shared read-only interface
without broadening its output guard. Unknown97.00 is still unknown. These H/I
steps do not complete Beta5 parameter-family, MK1/Turbo or physical-sound
acceptance; J-W work and the external review/player gates remain separate.

### Verified execution checkpoint

B/C is complete for the maintained source. Historical GitHub instructions
and old downloads have visible warnings and current-source links; original
content, release tags/assets and accepted technical evidence remain preserved.

D source integration is complete at
[`2ac8f5f`](https://github.com/Axelman8/ToneCommand/commit/2ac8f5fbbdc4be2416c205142ab5fa11b716060c),
reconciling upstream1.6.2 at4d81851. The maintained branch was fast-forwarded
to that exact tested tree and pushed. Final results on that source:6,960
passed/19 skipped,778 mandatory/targeted passed, one informational Windows
read-only USB enumeration warning. A fresh Windows CMD installation passed
its437 bootstrap checks/1 skip,169 installed checks, installed1.6.2 version
and resource smoke, and four mocked Chrome flows. Six additional actual
served-page checks verified the version/report fallback without JavaScript
at1440/390px. This is same-Windows software/installation acceptance, not a new
hardware, audio, other-machine or remote CI acceptance claim.

E now has native Settings language dropdowns in shared and workspace pages,
bundled EN/NL/DE, correct support links and script-free reports/version text.
The remaining shared write-workflow integration and player UX acceptance are
not declared complete. The two focused drafts289/290 are unchanged and remain
under upstream review; no draft was automatically approved or merged.

H-W were checked against the retained code and evidence. The75 older parameter
definitions survive in the earlier measured FW33 profile; definitions do not
prove complete workflows. Current Beta5 general writes remain blocked. Its
closed Gain/Mid fixture and existing-block Pitch proof do not approve the
other parameter/model/CAB/routing/controller/NAM/Store families. Accepted
older firmware tests are preserved rather than relabeled as Beta5 tests.

Next: obtain fresh unit-on/external-mute/desktop confirmation before native
continuation, then J's firmware-family checks and dependent K-W acceptance.
I's independent512-name comparison also remains open. F/G upstream review,
MK1/Turbo hardware, physical pedal direction and listening require their
respective owners. No new unit writes, Store, NAM installation, runtime
deployment or release occurred in this source-integration checkpoint.

The source-preparation and initial-audit notes below are historical checkpoints
where they differ from this verified execution status.

This is the single execution ledger for the maintained FX3 work. The older
seventeen-item table below is historical, profile-specific evidence, not a
claim that today's Beta5 app or MK1 supports every listed operation. Keep
historical acceptance; do not silently apply it to another firmware/runtime.

### Audit scope and factual status

Read-only audit of public project conversations in `Axelman8/ToneCommand`
and `monzta1/ToneCommand`: all525 upstream and26 fork issue/PR conversation
comments, all9 upstream inline comments (none on our PRs), zero fork inline
comments, reviews of our twelve upstream PRs, and review threads of the three
open reference/current drafts. All pages were exhausted. Relevant issue/PR
bodies, release metadata, current source and local evidence were compared.
Private messages, email and forum conversations were not inspected by this
GitHub audit. No hardware operation, GitHub reply, merge or release was made.

- Upstream main: `4d81851ecd163a984fd5dc3fc2cff9ad7a0f0dde`, release1.6.2.
- At audit time the full fork was local675f438, remoteb90f4da, based on1.5.16.
  B/C is now committed and pushed as `c593393` on the maintained source branch.
  D/E reconciles1.6.2 in an isolated preparation branch; final acceptance and
  transfer to the maintained branch must be recorded before calling it deployed.
- [PR289](https://github.com/monzta1/ToneCommand/pull/289) and
  [PR290](https://github.com/monzta1/ToneCommand/pull/290) are draft/open,
  mergeable, all15 checks successful on each current head. No submitted
  reviews or unresolved inline threads were found. PR290 contains the bridge
  dependency; reconcile it after289 lands, not by merging everything in270.
- [PR270](https://github.com/monzta1/ToneCommand/pull/270) is a reference-only
  draft. Its original body described old source/CI status; the current banner
  now identifies it as reference only and retains the original in a historical
  section. Wholesale merging270 is not the requested upstream delivery strategy.
- The [MK1 thread](https://github.com/Axelman8/ToneCommand/issues/1) now
  opens with current guidance and labels the original read-only assignment
  historical. It distinguishes the experimental one-scene writer and shared source. Old ZIPs
  remain immutable historical artifacts, not the current development branch.
- Latest MK1 tester reply found: successful-write report on24October.
  Acknowledged evidence is67 verified actions on preset70, source43666be,
  no Store. Independent model/route/level/listening results and the backend
  used remain requested. The owner later relayed a thin-lead complaint;
  its cause is not diagnosed by that write report.

### Requests already handled, do not reopen as new work

Execution update after the audit,28October: B/C source changes identify all
five app/test entry pages as Unofficial FX3, remove displayed logos/wordmarks
and logo favicons, and point support/report links to the fork. Script-disabled
Chrome checks and real served-resource tests cover those entries. Existing
read-only/experimental write boundaries are unchanged; no new installer or
hardware support is implied. Final source/package acceptance remains gated
by the regression and installation steps, not by these UI checks alone.

B/C acceptance at c593393: mandatory/changed572 passed,1 skipped; full6545
passed,19 skipped. A fresh installed Git clone passed117 capacity checks,
55 branding/diagnostic/language checks and script-disabled Chrome inspection
of all five entry pages, with zero logo/API requests. This proves that source
and local Windows installation scope, not other hardware, audible quality or
a new downloadable ZIP. Historical assets remain unchanged.

D/E preparation maps official read-only source to an explicit namespace and
preserves the full adapter/protocol. Connection-boundary tests verify close
before open, no reuse after failure and refusal of workspace writes on the
read-only context. Shared and workspace language controls are now native
Settings dropdowns. Workspace version/report fallback also works without
JavaScript. The source remains a candidate until its final regression,
installation and merge checkpoints are recorded. No new hardware writes.

Current guidance is now at the top of the
[MK1 coordination thread](https://github.com/Axelman8/ToneCommand/issues/1).
Six own obsolete setup comments are marked historical; a seventh retains
its open listening questions but corrects the old five-amp limitation.
[PR270](https://github.com/monzta1/ToneCommand/pull/270) is labeled reference
only and retains its original text in a historical section. All five older
fork release pages now warn HISTORICAL DOWNLOAD and link to the maintained
source. Release tags/assets/checksums and other contributors' messages were
not changed. Current source/doc publication is recorded separately from
these verified metadata updates.

| Request | Evidence/status |
|---|---|
| Small shared and read-only slices instead of merging270 |271/272 merged;270 remains the reference. Continue the same small-PR method. |
| Language in Settings, bundled translations, no fork-release link or extra installer in upstream |273 merged; verify the maintained full fork also adopts this UX during D/E. |
| Declared MK1 0..511 and MK2/Turbo 0..1023 name capacity |274 merged. This is read capacity, not Store permission or blanket hardware acceptance. |
| Hide the irrelevant III chassis picker |277 merged. Preserve detection-only visibility during D/E. |
| Checked output bytes, typed uncertain-write errors, final expiry check, literal name fixtures |278 hardening merged. Retain these invariants in every later operation. |
| Complete scene-name reads and fractional Amp literal tests |Maintainer284 merged; not an unanswered request for us to implement again. |
| Native Gain/Mid check and preservation of unused modifier metadata |287 merged after native/editor verification; all modifier words still preserved. |
| Offline336-model FW33 Amp catalog |288 merged. Catalog availability is not selector-write permission. |
| Two drafts, bridge then existing route/UI flow |289/290 merged by the maintainer on28October. Broader firmware/operation acceptance remains separate. |

### A-Z execution order

Status: DONE = scoped evidence exists; PARTIAL = code/evidence exists but the
exit criterion is not met; OPEN = work remains; REVIEW = upstream decision
pending. Dependencies are acceptance gates, not permission to change hardware.
No calendar deadline is promised before firmware and external-test gates pass.

| ID | Work package and current status | Depends on | Exit criterion and required help |
|---|---|---|---|
| A | Consolidate messages and evidence: DONE |None |Every relevant request has a source, status and owner in this ledger. Recheck for new replies before the next upstream handoff. |
| B | Unofficial branding and support: DONE at c593393 |A |All shipped test entry points, page titles, headers, favicons, controller/FX3 pages and previews are unmistakably Unofficial, contain no TC logo/wordmark styling, and link to the fork's own issue tracker. Retain legal attribution. Browser/resource tests cover every entry; no hardware needed. |
| C | One maintained source and clear download/start instructions: DONE for current source |B |One launcher/dependency set; exact source/version visible. Update current guidance in270/issue1 and distinguish source checkout from historical ZIPs. Do not overwrite old tags/assets or the tester's changes. No hardware needed. |
| D | Reconcile current upstream foundation: DONE at2ac8f5f, source scope |C |Controlled integration of current main, not a second app. Preserve accepted FX3 features/profile evidence and upstream FM9 behavior. Resolve source conflicts, rerun regressions, update the foundation manifest honestly. No hardware for source work; hardware acceptance stays separate. |
| E | Shared minimal UX, localization and diagnostics: PARTIAL |D |Use the existing Settings Language dropdown and request/conversation/review stages. Hide unavailable devices; show chassis only when relevant. New UI text uses bundled packs, retaining protected English confirmations/technical identifiers and untranslated user/AI/device content. Problem reports work on III and on script-load failure, send users to the correct issue tracker, and exclude secrets. Browser/installed-resource tests pass. |
| F | Internal reviewed-edit bridge,289: MERGED |A |Maintainer accepted the bounded bridge. Preserve exact-frame, single-use, expiry and state gates; no broader firmware approval follows. |
| G | Existing REVIEW/CONFIRM/SEND route/UI wiring,290: MERGED |F |Maintainer accepted the shared wiring. Player clicks SEND; no III sweep, false Undo/tone-check claim or second MIDI owner. New native firmware acceptance stays operation-specific. |
| H | Explicit firmware/chassis capability matrix: PARTIAL |D |Distinguish MK1/MK2/Turbo and exact builds. Keep32.06/earlier33 evidence without unconditional version aliases. Known Beta5 fingerprint is named; unknown raw97.00 remains unknown. Facts-only registry, capabilities and simulator name unsupported territory instead of pretending. Published matrix says read, write, measured and experimental separately. MK1/Turbo proof needs their owners. |
| I | Finish outstanding read-only acceptance: PARTIAL |H |Compare all512 upper MK2 names512..1023 independently with Axe-Edit; the successful1024-name native scan and boundary screenshots are not that comparison. Retain/refresh upper-range read/navigation evidence on the target revision. Verify declared-capacity boundaries without querying nonexistent MK1 slots or implying upper-slot Store. MK1/Turbo checks need external hardware. |
| J | Beta5 parameter families: PARTIAL |G,H |Promote only independently captured/read-back-verified operations. The closed Gain/Mid four-literal fixture is not general Amp/EQ/Delay/Reverb/level/zero/tempo support. Verify every proposed family, refusal and preservation on native hardware plus Axe-Edit. Owner MK2 can be used autonomously while muted/access granted. |
| K | Amp model choice and refresh: PARTIAL for current Beta5 |J |336-name catalog reaches the planner; selected models/reset behavior and quiet transitions verify independently. Refresh cannot approve unknown encodings. Model-specific voicing and full-state preservation pass; retain other-channel settings. |
| L | Legacy Factory/User cabs and mixer: PARTIAL for current Beta5 |J |Catalog selection agrees with active IRs, mode, bank and slot; four-slot level/pan/mute preserve unrelated state. MK1 User2 remains NAM-reserved, MK2 User2 remains usable. Name import is not IR installation. Dyna-Cabs stay separately scoped. |
| M | Normal AMP/CAB chain construction: PARTIAL |K,L |A normal text request can build a bounded connected route from an empty preset. Independently prove III geometry, cursor-before-insert and row/cable quirks, add/connect/remove operations, complete route checks and no silent overwrite of an existing graph. Do not inherit FM9-only topology evidence. Free graphs/feedback paths are a later declared scope. |
| N | One-to-eight-scene realization: PARTIAL |M |Names, channels, bypass and model/parameter settings match the musical brief. Shared voices are explicit; unintended duplicate scene sounds are rejected. Preserve other scenes. Eight scenes are not automatically eight independent Amp channels. |
| O | Wah/Volume and user controller choice: PARTIAL for current Beta5 |J,N |Chosen External1/2 bindings, ranges, supported Auto Engage and scene behavior pass the normal workflow and full modifier-table checks. Do not alter the user's global CC mapping. Physical sweep/bypass acceptance needs the player. |
| P | Pitch placement, octave pedal and Auto Engage: PARTIAL |M,O |Today's isolated placement/setup and private Fast Pos/Off proof become reviewed normal planner/scene operations with a visible supported scope. Bright wah versus pitch transposition gets clarification. Do not generalize the disconnected327 fixture. Physical controller and audible pitch tests need the player. |
| Q | Additional measured effects: PARTIAL |J,M,N |Drive/Compressor/GEQ/Chorus/Delay/Reverb are configured, not merely named or placed. Add further required guitar effects/instances only with selector, units, timing, modifier and channel preservation proof. Unsupported requested effects cause clarification, never silent substitution. |
| R | Musical planning, conversation and refinement: PARTIAL |E,N,Q |Artist/album/role requests lead to supported, justified sound choices and meaningful contrast. Clear missing-information questions; SEND sends the answer, Enter inserts a newline, drafts/restart work. Listening feedback can propose bounded adjustments through the same review path. No claim of hearing/exact reproduction from metadata. |
| S | Audio/link requests and route exploration: PARTIAL |R |A URL in the request or uploaded clip reaches the same design conversation; chosen audio window/measurements survive refinement. Offer supported AMP/CAB and NAM options without making NAM mandatory. Explain mixed-audio/measurement limits. Test the real configured AI and browser; listening quality is separate. |
| T | MK2 NAM inventory/selection/install slices: PARTIAL for current Beta5 |H,M |Split inventory, preset selection and native install into small PRs. Recognize occupied slots001..256, propose free choices, obtain destination/overwrite consent and verify complete installed contents. Permanent NAM writes are separate from SEND/Store. No runtime dependence on Axe-Edit. Preserve slot evidence and authorized memory boundaries. |
| U | TONE3000 account/search workflow: PARTIAL integration |T |Separate account contribution; user-owned login/entitlement, clear publishable-key help, safe token storage/refresh, no secret or weight publication. Search/download/model suitability are verified separately. All account labels localized; no unproven format conversion or fallback. |
| V | Existing-preset refinement and saved designs: PARTIAL |N,R |Freshly inspect the actual preset, reuse safely, disclose shared channels, preserve outside-scene state and retain supported design intent across restart. Do not treat cached text as current hardware or blindly rebuild an unknown third-party route. |
| W | Store, backup and recovery: PARTIAL |V |Separately confirmed storage, target/range checks, save/read/reload evidence and honest Undo scope on the final revision. Upper MK2 addressability does not expand Store allowlists. An uncertain write stops: no automatic retry, rollback write or reload. Recovery exports remain private. |
| X | MK1 evidence and musical quality: PARTIAL, parallel track |B,C,H |Keep one maintained source and the exact experimental firmware gate. Ask for missing independent comparison/listening, request/settings and monitoring context, plus whether the Copilot-only question remains blocking.336 software model choices are not336 native passes. Expand CAB/effects/scenes incrementally with the tester's own targets/consent; no inferred MK2 parity. External MK1 owner required. |
| Y | Release hardening and user acceptance: OPEN |D-W for declared scope;X for MK1 claims |Freeze source/scope, full/mandatory tests, actual per-head CI, clean Windows install, installed assets/languages, provenance, dependency/license/secret audit. Classify skips/environment failures. Run text/audio/clarification/review/SEND/refinement/Store and failure/reconnect UX on the exact candidate. Owner performs low-level listening/pedals; MK1 tester verifies declared MK1 scope. |
| Z | Immutable RC, sign-off and initial release: OPEN |B,C,Y |Explicit support matrix, known limits, checksums, first-use guide, test log, correct support links and fresh version. Owner signs off the candidate. Prefer official releases as slices land; any fork test distribution remains clearly Unofficial without TC logos. Publish a new artifact, never silently replace an old package. |

X can run in parallel as soon as B/C/H's relevant MK1 parts are ready; it
does not wait for MK2 NAM/accounts to finish. F/G's review does not block
offline preparation, but their upstream merge is not assumed. No blanket
"all firmware/all effects/all MK1" release claim follows from this plan.

### Follow-on tasks, retained rather than silently dropped

These are not prerequisites for a bounded Windows/MK2 Legacy AMP/CAB initial
release. If included in a release's advertised scope, they need their own
acceptance first; otherwise mark them unavailable/experimental explicitly.

- **Z1 Dyna-Cabs:** mode, catalog, microphone/position and impedance/mixer
  behavior, native/editor comparison, then planner support. Resource installation
  alone is not TC capability. Maintainer explicitly allows this after Legacy.
- **Z2 MK1 NAM:** separate hardware assignment, exact storage/slot evidence,
  explicit backup/overwrite consent and native/editor/full-memory comparison.
  The current roadmap says128 MK1 slots replacing all User2, versus256
  separate MK2 slots; verify before enabling anything. Do not assume250..256
  MK2 test permissions or addresses exist on MK1.
- **Z3 Broad graph/effect coverage:** more instances/channels/models, faithful
  parallel/stereo/four-cable paths, Send/Return and feedback-loop prevention.
  Preserve unsupported requirements rather than compiling a different rig.
- **Z4 Further runtime/device acceptance:** Turbo hardware, additional
  platforms/Python/MIDI backends, unknown firmware and safe upper-slot Store.
- **Z5 Audio matching:** guitar isolation, aligned reference/unit recordings,
  calibrated proposal/re-measure loops, real stereo/dynamics and listening.
  Never invent a measured dB-to-knob relation or change global USB routing
  without a separately verified and authorized operation.
- **Z6 NAM/library lifecycle:** safe usage indexing/deletion, broader
  multi-capture/multiscene builds, lawful supported model formats, gallery/
  preset/IR installation paths. Inventory alone is not safe deletion/install
  support. These need their own memory permissions and small review slices.

### Sources and operating rules

- [Maintainer's contribution/UX/release conditions](https://github.com/Axelman8/ToneCommand/issues/2#issuecomment-6458049718).
- [Original adapter, protocol, simulator and hardware-log acceptance contract](https://github.com/monzta1/ToneCommand/issues/190).
- [Bundled Settings language request](https://github.com/monzta1/ToneCommand/pull/273#issuecomment-6351148604).
- [Capacity follow-ups:512-name comparison, firmware label, MK1/Turbo](https://github.com/monzta1/ToneCommand/pull/274#issuecomment-6365072346).
- [Name-writer four-point hardening](https://github.com/monzta1/ToneCommand/pull/278#issuecomment-6379098765).
- [Maintainer's completed fractional/scene-name follow-up284](https://github.com/monzta1/ToneCommand/pull/284).
- [Native Amp/catalog follow-up accepted](https://github.com/monzta1/ToneCommand/issues/190#issuecomment-6397838937).
- [MK1 successful-write report](https://github.com/Axelman8/ToneCommand/issues/1#issuecomment-6384271378).
- [Outstanding MK1 listening/backend questions](https://github.com/Axelman8/ToneCommand/issues/1#issuecomment-6396639124).
- [MK1 musical-quality evidence request](https://github.com/Axelman8/ToneCommand/issues/1#issuecomment-6436532964).
- [Agreed public roadmap and release boundary](https://github.com/Axelman8/ToneCommand/issues/2).

Each future task records exact commit/profile, tests, native/editor evidence,
preserved state, remaining limitation and communication link. Implemented,
hardware-verified, upstream-merged, packaged and user-accepted are different
states. Do not count one as another. Preserve every accepted historical test.
Contribute device/firmware-specific protocol notes and a reproducible hardware
regression summary in the relevant small PR; mark unmeasured claims UNDECODED.
Keep firmware/bootloader traffic structurally unreachable and existing preset,
CAB and NAM allowlists unchanged. Never port an FM9 source ordinal, cable
encoding or plausible-but-stale GET result as III evidence without measurement.
Player-facing SEND remains a deliberate player click; autonomous development
permission is not permission to make ordinary user presets auto-send.

This ledger update does not publish a new test kit, contact a tester, alter
firmware/capabilities or authorize hardware operations. Source changes stay
separate from documentation/planning acceptance.

## Historical seventeen-item inventory

Owner requests all seventeen inventory items, 2026-10-16. This is an acceptance
ledger, not a claim that unmeasured writes are available. The maintained checkout
is the integration branch. FM9 behavior and permanent-storage allowlists stay
unchanged. MK2 hardware does not prove MK1 or other firmware compatibility.

| # | Work | Current acceptance |
|---|---|---|
| 1 | All amp models and refresh | Complete in the measured FW33/MK2 eight-scene route: 336 models, normal SEND, independent editor checks. |
| 2 | Full Factory cab catalog and selection | Integrated 2048 names; fixed native replay and actual AI/normal SEND pass within measured FW33/MK2 route. |
| 3 | Full User banks and separate FullRes | Correct FW33 addressing and whole-bank MK1 protection; normal User1/2 SEND and independent editor pass. FullRes names/restrictions separate, no occupied FullRes audition claimed. |
| 4 | Four-slot cab mixer and stereo | All four slots and A-D: captured/native mode, selector, level/pan, actual339-action SEND and independent eight-scene editor checks pass. |
| 5 | Drive, compressor and post-EQ | T808 Mod, Modern VCA Compressor and10 Band Variable Q A-D released within the measured route. Actual selected-AI536-action normal SEND and independent16-effect/eight-scene editor comparison pass, following379-step calibration. Exact grammar, typed bypass, manual compressor modes and cut-only EQ remain enforced. Other models and PEQ planner insertion remain separate; PEQ1/A numeric setters are independently migrated. |
| 6 | Additional effects and model selection | First-instance configurable effect coverage needs measured expansion. |
| 7 | Additional block instances/channels | Native layouts and preservation need measurement per supported family. |
| 8 | Free route construction | Developer graph evidence exists; normal route planner/executor not generally enabled. Send/Return separately guarded. |
| 9 | One to eight scenes | Released on the measured fixed AMP/CAB route after native prefix1..8 normal SEND with complete full-state/outside-scene checks and separate post-batch eight-scene editor comparison. Compiler/grammar/history/Store/UI agree on the count. This does not prove empty-grid construction for every count or general routing. Narrow serial/NAM paths remain separate. |
| 10 | Controllers/modifiers | Wah1/2 External1/2 and Off/Fast Pos are accepted in the separate controller workspace. Cry Babe/Wah1 shared-A voicing, scene bypass and controller binding now pass normal four-scene AMP/CAB review/SEND and independent editor comparison. Volume/Pan1 full-range/Off controller review/SEND is independently accepted too, but the fixed tone-planner route does not insert Volume. Global CC maps remain user-owned. |
| 11 | Tempo sync and exact zero | The earlier72-literal Amp/Delay/Chorus acceptance is retained. Sixteen further editor literals and normal full-state checks retain the approved Wah, Amp/Output Level and Reverb Mix zero variants. Reviewed AMP/CAB builds verify/set Tempo NONE before literal timing. New enum domains and global BPM remain separate. |
| 12 | Persistent designs and existing-preset refinement | Successful AMP/CAB designs and requested counts1..8 persist privately. Cold resume verifies every requested scene; independent native eight-scene full-state acceptance passes. Arbitrary third-party preset adoption remains unsupported. |
| 13 | Multi-capture/multiscene NAM | Native install and narrow builds exist. Broader selection/build support pending. |
| 14 | Audio segments, isolation and comparison | Explicit windows up to60 seconds and channel-power-v2 local analysis pass realChrome anti-phase/alias tests. Optional local recording comparison reports descriptive numerical differences only. Sanitized reference metrics survive verified history resume. Guitar isolation, musical alignment, direct unit recording and sound matching remain pending. |
| 15 | Save As, backup and recovery | Narrow Store proofs exist; general recovery must never retry an unknown write automatically. |
| 16 | Firmware/chassis/platform coverage | Exact FW33/MK2 native write path now explicitly pins Windows/Python3.12/mido; other runtimes remain read-only. MK1/other firmware/backends need their own acceptance, not inherited FM9 proof. |
| 17 | Publication acceptance | CAB checkpoint passes fresh checkout/venv/install and HTTP/resource smoke on this Windows machine. Candidate restart/browser checks pass. Other-machine/platform and remote CI/PR acceptance remain pending; no publication performed. |

## Execution boundaries

Use presets 321-329 for authorized tests, preserving 326 and 328 as references.
Shared NAM test storage is limited to 250-256. No IR memory, globals, firmware,
drivers or bootloader writes. External audio stays muted. One MIDI owner at a
time. Stop on unknown write results; no alternate opcode, retry, rollback or
preset reload. A snapshot or test pass never proves safe physical loudness.

## User bank memory policy

The separate MK1 NAM verification task is parked until an external MK1 tester
is available. See [the MK1 test assignment](AFX3-MK1-NAM-TEST.md). It does not
block the owner's [MK2 UX user test](AFX3-UX-USER-TEST.md). Publication-plan
steps 4, 5 and 6 follow that user test; those numbers are not the inventory
item numbers in the table above.

The official FW33 beta release notes specify the entire User Cab Bank2 is
replaced by NAM memory on MK1, not partly shared. MK2 has separate NAM storage
and retains User2. Unknown NAM-era hardware fails closed. Name imports never
install IRs or NAM models. Correct metadata does not itself authorize a write.

## Evidence before completion

Each hardware feature requires exact identity, scoped native execution,
independent display/full-state readback, unrelated-state preservation and an
independent Axe-Edit comparison. Store/reload, physical listening/controller
tests, other-platform installation and remote CI are separate acceptance steps.

## Interactive measurement requirement

Earlier desktop interruptions were subsequently resolved and the closed379-step
calibration plus independent12-channel editor comparison completed. During the
current autonomous continuation, foreground/screenshot access became unavailable
again. New post-native editor acceptance requires a restored interactive session.
An inaccessible session is not a hardware failure or permission to bypass
Windows security; new release flags remain disabled until actually verified.

The2026-10-18 session was accessible again. All75 approved FW32.06 parameter
definitions are retained in FW33, plus8 additions, behind explicit captured
encoding corrections. Wah tone-planner integration, Volume controller migration
and inherited scalar-zero variants passed their separate acceptance checks.
The remaining workflow gaps are tracked in
[firmware migration](AFX3-FIRMWARE-MIGRATION.md); complete parameter names do
not imply complete model, instance, channel, topology or raw-restore support.

## History and audio acceptance boundaries

History contains design metadata and fingerprints, not saved executable actions,
provider credentials or persistent SEND/Store consent. Resuming requires the
currently selected target, fresh external-mute consent and an unchanged complete
designed-scene survey. A mismatch stops without rollback or preset reload. Disk
failure cannot turn a completed SEND into a retry. CAB name caches are separate
per chassis and survive reconnects, but never prove installed IR contents.

Selecting a reference window changes the measured samples, not the AI's ability
to hear an isolated guitar. Synthetic browser tests verify range handling and
invalidation only; no live reference-versus-unit sound-match claim follows.
