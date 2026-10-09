# Install and setup

## macOS app (no Python)

The bundled macOS download contains `ToneCommand.app` and its own Python, so
Python and a terminal are not needed. The first chunk is not signed by an identified developer. After downloading and unzipping it, open the app; if
macOS says it cannot verify the developer, Control-click `ToneCommand.app`,
choose **Open**, then choose **Open** again. The app opens its local page at
`http://127.0.0.1:8909`. This bundle is macOS-only; Windows builds and signing
are planned for later chunks.

ToneCommand runs on **macOS, Windows and Linux**. macOS is the tested path;
Windows and Linux are documented and expected to work. Pick your OS below.

## Supported installs

ToneCommand runs from a **checkout** (clone the repository, then
`pip install -e .` inside it, exactly as below) or from the **bundled app**.
A plain `pip install .` (or installing the wheel) is not supported yet: the
wheel does not carry the data the app reads (`config/`, `ui/`, `recipes/`),
so it stops at startup with one line saying so rather than crashing (#177).
Making that install work is part of #208.

## macOS

Tested on Apple Silicon with Python 3.12 and an FM9 connected over USB, on
firmware 11.00 and 12.00.

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

The Windows walk-through has its own page, so it can be shared as one link
with someone who has never used a terminal:

**[tonecommand.com/windows](https://tonecommand.com/windows/)**, which is
[docs/WINDOWS.md](WINDOWS.md) in this repository.

Five steps, about ten minutes: Python 3.12, Fractal's USB driver, the ZIP,
a terminal in that folder, three lines. Troubleshooting for every error
reported so far is on the same page.

## Linux

Untested by the maintainer, expected to work. The steps match macOS, with one
prerequisite: the MIDI library (`python-rtmidi`) is compiled against ALSA, so a
bare system needs a compiler and the ALSA development headers before the pip
install can build it.

```bash
sudo apt install build-essential libasound2-dev python3-venv   # Debian/Ubuntu
# Fedora/RHEL: sudo dnf install @development-tools alsa-lib-devel python3-virtualenv
# Arch:        sudo pacman -S base-devel alsa-lib
git clone https://github.com/monzta1/ToneCommand.git
cd ToneCommand
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/tonecommand
# open http://127.0.0.1:8909 with the FM9 connected and powered on
```

Linux notes:

- No vendor driver is needed: the FM9 shows up as a standard USB-MIDI (ALSA)
  device. If its ports do not appear, confirm your user can access the device;
  USB-MIDI is normally reachable without extra permissions on a modern desktop.
- Instant cable-detection is macOS-only (CoreMIDI). On Linux the link falls back
  to the five-second poll and the reconnect pill, the same as Windows.
- For video builds, install ffmpeg with `apt install ffmpeg` (or your distro's
  package manager) instead of Homebrew.
- The guided one-click setup for the ChatGPT subscription route is Homebrew-
  based; on Linux install
  [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) by hand as its own
  documentation directs, or use any key-based service, the Claude CLI, or a
  local model, which need no helper at all.

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

## TONE3000 sign-in (optional)

A recipe can use a capture from TONE3000 by reference. To fetch one under
your own account, sign in once from ToneCommand:

1. In your TONE3000 settings, generate an API key pair and copy the
   **publishable** key (`t3k_pub_...`). If your account has any redirect URIs
   registered there, add `http://127.0.0.1:8909/api/tone3000/callback`.
2. Put `TONE3000_PUBLISHABLE_KEY=t3k_pub_...` in `.env` next to
   `TONECOMMAND_STORE_SLOTS` and start ToneCommand again.
3. Settings, TONE3000, SIGN IN. A tab opens on tone3000.com; sign in there
   and it sends you back. The tokens stay in `~/.tonecommand/tone3000_tokens.json`
   (readable by you only) and refresh themselves.

Nothing paid or private is fetched through ToneCommand: a capture your
account cannot reach shows its link and TONE3000's own flow to check your
access or pick a replacement. SIGN OUT deletes the tokens.

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

**Python 3.11 or newer on every platform, no compiler needed.** On 3.11 and
3.12 the MIDI binding is python-rtmidi; from 3.13 it is supriya-midi, which
ships prebuilt wheels to 3.14. `fm9/midi_transport.py` picks whichever
imports, and `TONECOMMAND_MIDI_BACKEND` (`mido` or `supriya`) forces one.
Both passed the same hardware pass on an FM9 (issue #172,
`tools/transport_pass.py`): status, block reads, the routing globals, a
preset loaded into the edit buffer and a user cab install all matched.

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

Other supported devices, and what each can actually do, are in
[DEVICES.md](DEVICES.md): the BOSS IR-2 (full control of all seven
parameters, verified by read-back, decoded on hardware 2026-09-29), the
HeadRush, and the ToneX (read-only by design).

Hardware: developed and regression-tested on an FM9 Mk II Turbo. Other
FM9 variants share the model byte and should behave identically, but are
untested. The FM3 has no MIDI over USB and needs a USB MIDI interface on its
5-pin MIDI ports (see DEVICES.md, #221); the Axe-Fx III uses a different
model byte and is not supported. Firmware outside 11.x / 12.00 is untested; the editor
protocol is unofficial and firmware-sensitive, and the hardware
regression suite passing is the green light after any update. The
original protocol feasibility findings, with the exact commands and
responses observed, are written up in
[HARDWARE-VALIDATION.md](HARDWARE-VALIDATION.md) - a dated
snapshot from 2026-08-16, kept as a record rather than maintained; the
living protocol record is [PROTOCOL.md](PROTOCOL.md).
