# Local audio evidence and descriptive comparison

The FW33 workspace advertises audio analysis version2. Its browser measures the
selected0.25-60 second window locally, at most eight decoded channels. Original
full-band samples supply RMS and sample peak. Channel powers are kept separate,
so opposite-phase stereo does not cancel before analysis. These are digital
file levels, not calibrated physical output levels or distortion-gain targets.

Before16kHz spectral sampling, an explicit normalized Blackman-windowed sinc
filter limits the spectrum to at most7kHz. FFT features are energy-weighted
across channels and windows. Analysis yields periodically to keep the browser
responsive. Real Chrome fixtures cover opposite-phase440Hz stereo and a
440Hz/12kHz mixture; browser interpolation alone failed the latter alias test.
These synthetic fixtures are not a measured reproduction of a musical rig.

The optional right-rail `OPNAME VERGELIJKEN` widget accepts an existing local
recording, not a microphone stream. It measures both selected windows and sends
only metrics to the local comparison endpoint. It never plays sound, changes a
preset, calls an AI or accesses MIDI. The response describes recording minus
reference: RMS, peak, crest, spectral centroid and five energy bands. Missing
band power produces an undefined ratio, not an infinite number. Incompatible
analysis methods/filter cutoffs and silent clips are refused.

This is deliberately not a tone-match score. Different notes, performances,
instruments, backing tracks, microphones and capture gain can explain the
differences. TC does not prove isolated guitar, aligned performances, that the
file actually came from the unit, or equal physical loudness. No numerical
comparison authorizes an automatic gain boost or SEND.

Successful designs may keep bounded numeric reference evidence in private
version2 history. URLs and file names are removed. Older version1 designs
remain readable. Cold resume still verifies every designed scene and requires
fresh target/mute confirmation; stored metrics carry no executable actions or
SEND/Store authority. Refinement labels reused evidence as a previous supplied
measurement, never new listening. A new link still requires fresh matching
analysis. Older backends continue the legacy browser measurement path without
claiming version2 provenance.

Guitar isolation, device-output capture, musical time alignment, delay-timing
estimation and auditory acceptance are separate unfinished features.
