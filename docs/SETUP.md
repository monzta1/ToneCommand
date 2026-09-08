# Install and setup

ToneCommand runs on **macOS, Windows and Linux**. macOS is the tested path;
Windows and Linux are documented and expected to work. Pick your OS below.

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

**No experience needed. Five steps, about ten minutes, most of it waiting for
downloads.** You will type three lines at the end. You can copy and paste them.

Untested by the maintainer and expected to work: it is all cross-platform
Python, and the one macOS-only piece (instant cable detection) falls back to
checking every five seconds. If you try it, please say how it went in an
issue, either way.

### Step 1: install Python

Get it from **https://www.python.org/downloads/windows/** and run the
installer.

> **On the first screen, tick the box that says "Add python.exe to PATH"**,
> down at the bottom, before you click Install. This is the single most common
> thing to get wrong, and skipping it is why "python is not recognised"
> appears later. If you miss it, run the installer again and choose Modify.

Any version 3.11 or newer works.

### Step 2: install the FM9 USB driver

Download Fractal's Windows USB driver from
**https://www.fractalaudio.com/fm9-downloads/** and install it.

This is the same driver FM9-Edit uses, so **if FM9-Edit already works on this
computer, you can skip this step.** Without it, Windows cannot see the FM9 at
all and ToneCommand will say it cannot find your unit.

### Step 3: download ToneCommand

Go to **https://github.com/monzta1/ToneCommand**, click the green **Code**
button, then **Download ZIP**.

Then find the downloaded file (usually in your Downloads folder), right-click
it, and choose **Extract All**. You now have a folder called
`ToneCommand-main`.

### Step 4: open a terminal in that folder

Open the `ToneCommand-main` folder so you can see the files inside it
(`README.md`, `server.py` and so on).

Now **hold Shift, right-click on any empty white space in that folder**, and
choose **"Open PowerShell window here"** or **"Open in Terminal"**.

A window with a black or blue background opens. That is the terminal. It is
just a place to type commands. Nothing you do in the next step can damage your
computer or your FM9.

### Step 5: type these three lines

Type or paste **one line at a time**, pressing Enter after each, and wait for
it to finish before starting the next.

```powershell
py -m venv .venv
```

*Makes a private space for ToneCommand's parts, so it cannot disturb anything
else on your computer. Takes a few seconds and prints nothing. That is normal.*

```powershell
.venv\Scripts\pip install -e .
```

*Downloads the pieces it needs. This is the slow one, usually one to three
minutes, and it prints a lot of text. Scrolling text is good.*

```powershell
.venv\Scripts\tonecommand
```

*Starts ToneCommand. Leave this window open: closing it stops the program.*

### What you should see

The last command prints a line ending in something like:

```
Uvicorn running on http://127.0.0.1:8909
```

Now open your web browser and go to **http://127.0.0.1:8909**

With the FM9 switched on and plugged in by USB, the link indicator at the top
of the page turns green and names your preset. That is it: you are running.

### Using it again tomorrow

You only do steps 1 to 4 once. After that:

1. Open the `ToneCommand-main` folder.
2. Shift + right-click, **Open PowerShell window here**.
3. Type the last line only:

```powershell
.venv\Scripts\tonecommand
```

4. Go to **http://127.0.0.1:8909** in your browser.

### If something goes wrong

**"py is not recognised"** or **"python is not recognised"**
Python is not installed, or the PATH box in Step 1 was not ticked. Run the
Python installer again, choose **Modify**, and make sure **"Add python.exe to
PATH"** is ticked. Then close the terminal window, open a new one, and try
again. A terminal only notices the change if it was opened afterwards.

**"cannot be loaded because running scripts is disabled"**
Windows is blocking the command. Paste this once, press Enter, answer `Y`,
then run the failing line again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**The page loads but the link indicator is red, or it says it cannot find the
FM9**
Check, in this order: the FM9 is switched on; the USB cable goes from the FM9
to the computer and is a data cable rather than a charge-only one; Fractal's
driver from Step 2 is installed; and FM9-Edit is **closed**, because only one
program can hold the FM9's USB connection at a time.

**"port 8909 is already in use"**
ToneCommand is already running in another window. Use that one, or close it
and start again.

**Anything else**
Open an issue at **https://github.com/monzta1/ToneCommand/issues** and paste
the red text. The exact wording matters, so copy it rather than describing it.

### Notes for later

- For video builds, install ffmpeg with `winget install ffmpeg` instead of
  Homebrew.
- The guided one-click setup for the ChatGPT subscription route is
  Homebrew-based, so it is macOS only. On Windows, either install
  [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) by hand as its
  own documentation directs, or use any key-based service, the Claude CLI, or
  a local model, which need no helper at all.

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
