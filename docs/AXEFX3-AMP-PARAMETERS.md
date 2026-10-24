# Opt-in Axe-Fx III Amp parameter experiment

Small follow-up to #278, separate from the accumulated implementation in #270.
This is an explicitly constructed developer component, **not a normal GUI,
planner or production write capability**. The application still constructs the
ordinary read-only adapter. No server route, dependency or registry is changed.

## Scope

`AmpEdit(preset, 'gain' | 'mid', value)` pins one current wire preset and one
Amp 1/channel A control. Values are finite 0.1-8.0 in steps of 0.1. A review
permits a change of at most one display unit from the independently read value.
Unsupported values are refused, not clamped. No zero/alternate setter, model,
channel, scene, bypass, routing, level, NAM, controller, Store or global write.
Other scenes sharing this Amp channel may hear the resulting change.

Only the exact measured MK2 `33.00-beta.20261006` identity is admitted, pinned
separately by full-reply SHA-256. Raw 97.00 alone, MK1, Turbo and other builds
do not enable this component. The chassis remains a caller declaration, not
automatic hardware identification. No future name-writer firmware change
automatically promotes this parameter encoding.

The encoding reference is the prior MK2 FW33 work in
[the full-fork snapshot](https://github.com/Axelman8/ToneCommand/blob/b76019983fba2e699db7fc4fdeab85d2be3f7413/docs/FW33-COMPATIBILITY.md),
not the FM9 parameter catalog. Gain/Mid are Amp effect 58, parameters 1/3,
01/09 float32 display-before-divide-by-ten SETs. Amp data has four 142-word
channels. Bulk 1F replies and passive 01/10 numeric display queries are read
forms, never a zero SET disguised as a getter. Literal port-byte tests pin
Gain 4.0 and Mid 6.0 independently of the builder used by this component.

## Review and verification

`AmpWriter.review_amp(edit)` reads the complete existing name/status surface,
all 568 Amp words, all 32 complete 25-word inactive **unassigned** modifier
records and the passive numeric display. Amp 1 must exist and already use
channel A. Repeated Amp/status reads check coherence. An unreadable field,
assigned modifier or mismatched display declines before SET.

`apply_amp(review, external_audio_muted=True)` consumes a connection-owned
review, rereads and compares the baseline, and checks the 60-second deadline
again immediately before arming the exact single-use, thread-owned frame.
Transport receives a new plain MIDI message reconstructed from checked bytes.
No-op consumes the review without writing. Caller-created/replaced reviews,
changed context, missing consent and expired reviews are refused.

After the one SET, settling retries are **reads only**. Display must match
within 0.011, the target normalized word within one count, and every other
observed Amp word/modifier/status field must remain identical. A malformed or
incoherent read, other observed change, or transmission error reports that a
write may have happened and latches the connection uncertain. No SET retry,
automatic rollback, reload or Store. Reconnection is not a recovery write.

This observes Amp words, modifiers and names/block status. It does **not**
read the grid or all other blocks' parameter dumps, establish global controller
absence, prove full-preset preservation, or measure loudness/tonal suitability.
Conservative value/step bounds and external-mute acknowledgement are not a
physical limiter. Keep the unit untouched during the operation.

## Hardware acceptance still required

The extracted component's offline fake-port tests are not native acceptance.
It was not deployed over the full fork and this PR does not claim a fresh
hardware or listening pass. Prior full-fork measurements are encoding evidence,
not an independent regression of this extraction or another chassis.

A later authorized native test should use an existing Amp 1/A fixture with
unassigned modifiers, confirmed external mute and an explicitly approved
disposable preset. Record exact firmware/source, before/after complete Amp
and modifier data, passive display and preserved names/status. After releasing
TC MIDI, independently compare in Axe-Edit. Restore the original value only
as a separately reviewed operation. Do not save or reload automatically.
Audition and physical level checks are a separate, low-volume user step.
