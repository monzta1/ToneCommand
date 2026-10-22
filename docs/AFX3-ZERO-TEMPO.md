# Measured FW33 zero controls and automatic free timing

The exact FW33 beta20261006/MK2 profile now supports exact zero on the seven
core Amp knobs: Gain, Bass, Mid, Treble, Master, Depth and Presence. Amp LEVEL
still must remain at most-12dB in the reviewed AMP/CAB build. Zero is not an
invitation to write a loud output or replace an unrelated enum/model setter.

Delay1 Digital Mono A supports zero Feedback and Mix. Chorus1 Analog Stereo A
supports zero Depth and Mix. These are model-bound scalar controls; another
model or instance is refused before a reviewed build starts. Delay feedback0
corresponds to the midpoint of its bipolar bulk domain, not bulk word0.

During a reviewed AMP/CAB timing operation, TC can now verify a recognized
existing tempo division and set Tempo NONE before writing literal milliseconds
or Hz. The operation binds to the current design action, target, firmware,
model, channel and fresh complete state. It permits only NONE, not arbitrary
note divisions or global BPM changes. An unreadable or mismatched enum stops.
NAM and narrow serial-route preflights still require existing NONE separately.

When a synchronized numeric display contains a note suffix, TC first verifies
NONE, then settles the now-numeric display before its single value write.
Unrelated fields must stay unchanged. A failed or unknown result consumes the
operation; there is no alternate opcode, write retry, rollback or preset reload.
An active closed developer calibration is exclusive: a normally valid released
setter cannot bypass its exact recorded order or single-operation permit.

## Hardware acceptance, 2026-10-17

Closed UI-correlated captures provide60 Amp zero/restore/channel literals,
four Chorus/Delay quarter-note/NONE literals and eight FX zero/restore literals.
All72 replay with independent display/full-state checks and restored original
state. Separate Axe-Edit checks confirm the restored Amp voices before testing.

The first actual selected-AI333-action build correctly stopped before its time
write because a synchronized display could not be parsed. The resulting setter
ordering fix has a regression test using the real adapter method, not only a
mocked setter. A fresh complete state matched the known294 successful operations;
neither tempo transition nor the failed time write had been sent. A new plan
and review, not the old SEND token or an unknown-write retry, followed.

The new actual selected-AI/normal API SEND completes333 of333 actions on muted
test322, with no skipped actions or Store. Both Tempo1/4 values become NONE,
then Delay350ms and Chorus0.35Hz verify. All28 Amp knobs and four effect scalars
verify at zero. An independent Axe-Edit pass checks all four Amp channels,
models,28 zero knobs, both effect models, four scalar zeros, NONE and literal
timing. It returns Amp A and closes normally without Save or numeric edits.

This is technical acceptance, not a musical preset, physical-volume test,
audible tone match or support for every effect/model/parameter. The fixture is
left in322's edit buffer with Amp knobs at zero; presets326/328 are not written.
The corresponding release gates have no GUI or environment override. Startup
hash checks include the immutable calibration data and both new modules.
