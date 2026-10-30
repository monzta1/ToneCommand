# Axe-Fx III private design history and reference windows

## Continue a successful design after restarting TC

After a fully verified SEND of the measured FW33/MK2 one-to-eight-scene AMP/CAB mode,
TC saves the design and full-scene fingerprints locally. Expand **ONTWERP
HERVATTEN**, choose a record for the currently selected preset, confirm the
target and external audio mute, then select **CONTROLEER & HERVAT**.

TC checks the current state before switching scenes, independently checks all
requested scenes, then selects scene1 for listening-feedback adjustments. Draft text
is retained. It does not run an old SEND, call the AI, write effect parameters,
select another preset or Store anything just because a record was selected.
Every subsequent adjustment still needs its normal review and SEND consent.

A different preset, firmware, chassis, imported CAB names or scene state stops
resumption. No rollback, reload or guessed merge is attempted. This is not
general adoption of an arbitrary existing preset. Stored IR names/fingerprints
do not prove the contents or audible contribution of shared IR/NAM memory.

## Local files and privacy

The default directory is `~/.tonecommand/axefx3`; advanced/test installations may
set `TONECOMMAND_AXEFX3_STATE_DIR`. Records in `design-history` contain the
successful design, target and hashes. They contain no provider account tokens,
reference audio, IR/model weights, executable action stream or saved Store
authorization. Checksums detect corruption, not tampering by another process
running as the same account. Up to2000 records are retained without automatic
deletion; the GUI lists the latest50 readable records.

Imported CAB names persist in separate MK1/MK2 files in that private directory.
Refresh the imported names after changing device IR contents. Name persistence
does not install an IR and does not authorize using a reserved MK1 User2 bank.
Simulator tests must use an explicit isolated state directory and never inherit
the owner's private history or CAB cache.

## Reference audio window

Expand SONG/AUDIO and select a start time and length, in seconds. Analysis uses
that interval, up to60 seconds, bounded by the source duration. Changing the
range invalidates cached analysis and pending proposals; an out-of-source range
is refused before planning. Measurements state the actual start and duration.

The selected reference remains a mixed recording unless the user supplies an
isolated instrument. Windowing is not guitar separation or an auditory clone.
There is no automatic recording of the Fractal output or proven match here.

## Acceptance on the owner's exact FW33/MK2

- Normal339-action SEND creates a successful private history record on322.
- A cold canonical8909 runtime restores2112 imported CAB-name positions;
  the catalog contains2320 nonempty Factory/User choices.
- Actual GUI resumption independently surveys8 scenes, preserves draft text,
  exposes8 adjustment targets and sends no parameter, model, Store or AI call.
- A separate native reader forbidding every mutating frame verifies resumed
  scene1 against its original complete successful-SEND fingerprint.
- Synthetic browser clips verify window offsets, duration, cache invalidation
  and out-of-source refusal. These are not listening or loudness tests.

Other firmware/chassis, arbitrary preset adoption, physical loudness, guitar
isolation and cross-platform/remote installation remain separate acceptance.
