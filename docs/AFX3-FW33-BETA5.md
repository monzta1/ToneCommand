# FW33 public beta #2 (Beta 5): migration checkpoint

28October follow-up: [read-only labels/names](AXEFX3-READONLY.md) and
[eight bounded Amp-control measurements](AFX3-BETA5-PARAMETER-FAMILIES.md)
extend the evidence below. They do not enable the normal Beta5 writer.
The27October record remains historical where superseded by those dated checks.

Status: 27 October 2026. Exact identity recognition and read-only discovery,
**not new-build write support**. The initial-release roadmap and discussion:
[Axelman8/ToneCommand issue 2](https://github.com/Axelman8/ToneCommand/issues/2).

## Current independent evidence

- Owner reports firmware and Dyna-Cabs 1.10 installed and checked. Installed
  Axe-Edit is 1.15.02 and independently identifies the connected unit as MK II,
  FW33 beta. The native identity contains `Oct 26 2026 12:42:45`.
- Exact native identity SHA-256:
  `15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616`.
  Raw version fields still say 97.00; those fields alone cannot select a profile.
- Two complete read-only snapshots of empty current preset 327 agree. A second
  two-read pass on a separately editor-created, disconnected five-block fixture
  also agrees, including all 32 complete modifier records and eight scene names.
- Amp/Cab/Drive/Pitch/NAM full bulk counts are 568/424/176/464/72, consistent
  with the earlier four-channel strides. Equal lengths do not prove equal
  parameter meanings or compatible setters. No Input, Output or cables are in
  the measurement fixture. Reference presets 326/328 were not selected.
- The local editor cache has the same 336 Amp names and ordinals as the
  accepted earlier catalog. After a fresh editor connection, cache hash:
  `d29fd63af53a5b637e2ddbb652ac2f3ce858401281976ca58a3becefc9adf24d`.
  The initial existing cache was different. The fresh cache contains a 257th NAM
  enum entry with an empty scratchpad name, which broke complete AMP refresh
  parsing. The parser now permits only that final empty label for the exact
  observed tag60/pid0/type16/range0..256 record shape. Other empty labels remain
  invalid. Only Amp names leave the parser; this grants no scratchpad writes.
- Four literal editor Amp operations were captured independently: Treble Gain
  5 -> 4.6 -> 5, Mid 5 -> 5.6 -> 5, on 59 Bassguy Bright/A. The old typed
  float32-before-division encoder matches these captured bytes. Outgoing
  capture is not device readback; the observer captured no incoming buffers.
- The existing TC transport refused the first proposed native SET **before
  output** because there is no accepted new-build write path. Zero TC parameter
  SETs were transmitted. No guard was relaxed or firmware identity aliased to
  the earlier build to turn that refusal into a passing result.

## What recognition changes

`firmware_identity.identify` labels only the complete observed response as
`33.00-beta5.20261026`. The adapter uses that label instead of the misleading raw
97.00 fallback. Other replies keep the previous fallback, and the old exact
profile remains unchanged. Beta 5 is **not** added to `SUPPORTED_FIRMWARE` and
receives no writable definitions, model roster, NAM installation or edit session.
No production server is restarted or connected as part of this checkpoint.

## Required next steps

1. The separate [closed Amp calibration](AFX3-BETA5-AMP-CALIBRATION.md) now has
   software checks and candidate native/display/full-state/fresh-editor
   acceptance for four captured Gain/Mid values on disconnected327. The normal
   adapter remains unchanged and refuses writes. No old identity is aliased.
2. Review that bounded component and retain separately reviewed restoration.
   This is not yet a generic parameter setter or ordinary app SEND integration.
3. Extend verification by operation family: models, cab selection/mixer, grid,
   scenes, modifiers, timing/zero, NAM inventory/selection/install and Store.
   Keep unverified families blocked; retain old profiles and tests.
4. Reconcile the final upstream source and run actual registered UI/SEND,
   installation, CI, persistence and human listening acceptance before release.

Dyna-Cab automation has its own roadmap milestone. Resource installation is
not TC selector/microphone/positioning support. MK1 NAM has 128 slots and uses
User Cab Bank 2; MK2 has 256 separate slots. MK2 testing proves neither MK1
installation nor support for a scratchpad. Levels/feedback rules are not a
physical limiter or acoustic-feedback guarantee.
