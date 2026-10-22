# Axe-Fx III completion backlog

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
