## Scope

State the upstream base commit and what this PR actually changes. Keep shared
planner/UI improvements separate from device protocol changes where possible.

## Evidence

- [ ] Offline simulator/parser/validation tests (command, result, platform)
- [ ] Shipped UI tests, not only a mock of the UI
- [ ] Windows and Linux GitHub `tests` check passed
- [ ] Installed resource/package checks if changing distribution
- [ ] Hardware claims have the exact device/firmware, operation and independent
      readback recorded in public docs, with raw personal captures kept private
- [ ] Audible/physical controller acceptance is separate from readback

## Boundaries

- [ ] No preset/CAB/NAM whitelist expansion or never-brick guard change
- [ ] No FM9-specific write/reamp path exposed to Axe-Fx III
- [ ] Unverified firmware/models/routing remain blocked
- [ ] No private presets, account keys, imported personal IR lists, NAM weights
      or third-party guide prose in the diff or published history
- [ ] Release tripwire and manual license/security review completed
- [ ] Breaking changes, unsupported cases and migration/rollback documented

An unchecked box is an open gate, not a reason to claim that gate passed.
