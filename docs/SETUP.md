# Install and setup

Tested on macOS (Apple Silicon) with Python 3.12 and an FM9 connected over
USB, on firmware 11.00 and 12.00.

```bash
git clone https://github.com/monzta1/ToneCommand.git
cd ToneCommand
python3 -m venv .venv
.venv/bin/pip install -e .
```

Dependencies are declared in [pyproject.toml](../pyproject.toml); add
`".[dev]"` to also get the test tooling.

Run:

```bash
.venv/bin/tonecommand
# open http://127.0.0.1:8909 with the FM9 connected and powered on
```

## Windows

Untested by the maintainer, and expected to work: everything here is
cross-platform Python, and the one macOS-only piece (instant cable
detection through CoreMIDI) degrades cleanly to the five-second poll and
the link pill's reconnect. If you run it on Windows, please report how it
went, either way, in an issue.

```bat
git clone https://github.com/monzta1/ToneCommand.git
cd ToneCommand
py -3.12 -m venv .venv
.venv\Scripts\pip install -e .
.venv\Scripts\tonecommand
:: open http://127.0.0.1:8909 with the FM9 connected and powered on
```

Windows notes:

- The FM9 needs Fractal's Windows USB driver installed (the same one
  FM9-Edit uses) before its MIDI ports appear.
- For video builds, install ffmpeg with `winget install ffmpeg` instead
  of Homebrew.
- The guided one-click setup for the ChatGPT subscription route is
  Homebrew-based, so on Windows install
  [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) by hand as
  its own documentation directs, or use any of the key-based services,
  the Claude CLI, or a local model, which need no helper at all.

Planner configuration (which AI answers your sentences) is in
[AI-BACKENDS.md](AI-BACKENDS.md). The default needs nothing: a signed-in
Claude Code CLI is found on its own.

## Building from a video (optional)

The "build from a video or description" field takes pasted text and page URLs
with no extra setup. Reading a **YouTube link** needs more, and it is optional
on purpose:

```bash
.venv/bin/pip install -e ".[video]"     # yt-dlp and faster-whisper
brew install ffmpeg                      # or apt install ffmpeg
```

Three sources are tried, cheapest first: the video **description**, which is
where most players put their gear list; the **captions**, free and instant
where they exist; and failing both, the audio is downloaded and **transcribed
locally** with Whisper. Nothing is sent to a transcription service.

`ffmpeg` is a system dependency and pip cannot install it. It is only needed
for that last case. The app tells you at startup which of the three it can do
on your machine rather than failing at the end of a long wait.

Transcription is CPU only and measured on an M-series Mac at about 9.6x
realtime, so an hour of video is roughly six minutes. The `base` model is the
default for that reason; set `TONECOMMAND_WHISPER_MODEL=small` for better
accuracy on gear names at about a third of the speed. Videos longer than 90
minutes are refused rather than transcribed, with a suggestion to paste the
relevant part.

**Long videos are the normal case and are handled by compression, not by
patience.** A source is read into a compact spec before anything is built: a
5,286 word walkthrough became a 282 word brief in 49 seconds, keeping all
twelve of its tone statements and dropping the sponsor read. The expensive
build pass never sees the transcript.

## Testing

Testing is two-tier:

```bash
.venv/bin/pytest tests/                    # simulator + validation suite, no hardware needed (runs in CI on every push)
.venv/bin/python hardware_regression.py    # 13-check on-hardware regression; run after any firmware update
.venv/bin/python build_133.py              # example: scripted full preset build (stores to wire slot 133 = FM9-Edit 134)
```

## Running beside FM9-Edit

FM9-Edit can be open at the same time, but only one of you should be making
edits. This note used to say FM9-Edit resets the edit buffer when it connects;
that was tested and it does not. With an unsaved chain sitting in the buffer,
FM9-Edit 1.03.21 connected to an FM9 on fw 12.00 and the edits survived
intact, and twelve rounds of reads here stayed correct while the editor polled
the shared CoreMIDI port at ~60 messages/second. What actually discards buffer
edits is LOADING a preset - from FM9-Edit, the front panel, or this tool -
which is the ordinary mechanism rather than an FM9-Edit quirk. Two clients
writing the same parameters will still fight, and concurrent writes are
untested, so keep editing to one side at a time. Older FM9-Edit versions and
fw 11.00 are untested here. Stored presets are safe either way and remain
fully viewable and editable in FM9-Edit.

## Compatibility

Verified means proven by write-plus-readback on real hardware in this
project's regression runs; nothing below is assumed.

| Capability | FM9 fw 11.00 | FM9 fw 12.00 | Simulator |
|---|---|---|---|
| Scene, bypass, channel control | Verified | Verified (contributor) | Modeled |
| Parameter set with read-back verify | Verified | Verified (contributor) | Modeled |
| Expression pedal (modifier) binding | Verified | Untested | Modeled |
| Block insert and cable drawing | Verified | Verified | Modeled, incl. known encoding quirks |
| Store to whitelisted slots | Verified | Untested | Modeled |
| Tone library harvest (all 512 slots) | Verified | Untested | Modeled |
| Slot name read by number, no select | Verified | Verified | Modeled |
| Empty-slot detection (`<EMPTY>` marker) | Untested | Verified | Modeled |
| Preset built from scratch in an empty slot | Untested | Verified | Modeled |

Hardware: developed and regression-tested on an FM9 Mk II Turbo. Other
FM9 variants share the model byte and should behave identically, but are
untested. Axe-Fx III and FM3 use different model bytes and are not
supported. Firmware outside 11.x / 12.00 is untested; the editor
protocol is unofficial and firmware-sensitive, and the hardware
regression suite passing is the green light after any update. The
original protocol feasibility findings, with the exact commands and
responses observed, are written up in
[HARDWARE-VALIDATION.md](HARDWARE-VALIDATION.md) - a dated
snapshot from 2026-08-16, kept as a record rather than maintained; the
living protocol record is [PROTOCOL.md](PROTOCOL.md).
