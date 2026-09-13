# Offline IR and audio tranche delivery record

Date: 2026-09-13

This record identifies the tested two-repository pair for ToneCommand issues
#18, #73, #85, #90, #92, #93, #101, #102, #103, and #105.

## Compatible pair

- IRCommand: `3c211c38c3c1d2ae6b449240595023a08dc7701e`
- ToneCommand: `d953b348939c70871e2b3b8257596d8309403ec2`
- Post-commit compatibility check: 3 passed

IRCommand owns the closed reject-all and target-routing contracts. ToneCommand
keeps the FM9 boundary local, validates factory slots against its registry, and
uses only opaque IRCommand asset identities across the service boundary.

## Verification

- ToneCommand full offline regression: 1,630 passed
- IRCommand full offline regression: 431 passed, 2 skipped
- Final focused recovery and compatibility suite: 17 passed
- Final focused audio suite: 36 passed
- Independent Codex reviews: approved with no high- or medium-severity findings

The first IRCommand full run overlapped ToneCommand's parallel workers and
missed the scanner's five-second performance ceiling. The required uncontended
IRCommand rerun passed in full. No product defect was hidden or waived.

## Deployment and rollback

Deploy IRCommand first, then ToneCommand. An older IRCommand remains a supported
degraded case: ToneCommand offers Keep Current and a registry-validated local
factory fallback without recycling rejected selections.

Rollback both repositories as a pair:

- IRCommand pre-run commit: `d4488b1`
- ToneCommand pre-run commit: `f485fd6`

IRCommand is local-only and has no remote. ToneCommand ships from branch
`codex/offline-10-ir-audio`.

## Hardware boundary

`hardware_verified: false`

No FM9 was connected. Recovery and target preparation were verified as offline,
advisory, path-safe operations. The analysis engines for #101, #102, #103, and
#105 are implementation-complete against deterministic fixtures, but the issues
remain open pending FM9 capture and integration in #100. No live sound-check,
device write, or FM9 capture is claimed by this delivery.
