# ToneCommand on Windows

**No experience needed. Five steps, about ten minutes, most of it waiting for
downloads.** You will type three lines at the end. You can copy and paste them.

Every release runs the full test suite on Windows as well as macOS and
Linux, so what is written here is checked by machine on every change. The
maintainer's own unit is on a Mac, so the FM9 half is still proven by the
people who run it on Windows: if you try it, please say how it went in an
issue, either way. The one macOS-only piece (instant cable detection) falls
back to checking every five seconds here.

## Step 1: install Python

Install **Python 3.12**, not the newest one. The big download button on
python.org gives you the newest, which is too new: the MIDI library
ToneCommand uses ships prebuilt parts for Python 3.12 and older only, and on
a newer Python the install tries to compile it and stops with a wall of red
text about compilers. Go to
**https://www.python.org/downloads/windows/**, scroll to the list of
releases, pick the latest **3.12.x** "Windows installer (64-bit)", and run
it.

> **On the first screen, tick the box that says "Add python.exe to PATH"**,
> down at the bottom, before you click Install. This is the single most common
> thing to get wrong, and skipping it is why "python is not recognised"
> appears later. If you miss it, run the installer again and choose Modify.

3.11 works too. 3.13 and newer do not yet, and the install will say so in
one line ("requires a different Python"). The reason is the MIDI library
(python-rtmidi, no prebuilt parts past 3.12); a second library that has
them (supriya-midi) is wired in behind `TONECOMMAND_MIDI_BACKEND=supriya`
and the ceiling lifts once it has had its hardware pass on the unit
(issue #172). Until then, 3.12.

## Step 2: connect your unit (FM9: USB driver; FM3: a MIDI interface)

**FM9.** Download Fractal's Windows USB driver and install it:
**https://www.fractalaudio.com/fm9-downloads/**

This is the same driver FM9-Edit uses, so **if FM9-Edit already works on this
computer, you can skip this step.** Without it, Windows cannot see the FM9 at
all: Report a problem shows "MIDI in: none", and ToneCommand says this
computer sees no MIDI input at all.

**FM3.** The FM3 has no MIDI over USB: its USB port carries Fractal's own
channel for FM3-Edit, Fractal-Bot and Cab-Lab and never shows up as a MIDI
device, with or without a driver. Connect a USB MIDI interface to the FM3's
5-pin MIDI ports (interface OUT to FM3 IN, FM3 OUT to interface IN), then
choose that interface's port in the FM3 card on the Devices page.

## Step 3: download ToneCommand

Go to **https://github.com/monzta1/ToneCommand**, click the green **Code**
button, then **Download ZIP**.

Then find the downloaded file (usually in your Downloads folder), right-click
it, and choose **Extract All**. You now have a folder called
`ToneCommand-main`.

> **Download it fresh rather than reusing an older copy.** Versions before
> 1.5.3 stop on Windows with a `UnicodeDecodeError` before the program
> starts. The ZIP from that green button is always the current version, so a
> fresh download is already fixed. If you are stuck with an older copy, the
> workaround is at the bottom of this page.

## Step 4: open a terminal in that folder

Open the `ToneCommand-main` folder so you can see the files inside it
(`README.md`, `server.py` and so on).

Now **hold Shift, right-click on any empty white space in that folder**, and
choose **"Open PowerShell window here"** or **"Open in Terminal"**.

A window with a black or blue background opens. That is the terminal. It is
just a place to type commands. Nothing you do in the next step can damage your
computer or your FM9.

## Step 5: type these three lines

Type or paste **one line at a time**, pressing Enter after each, and wait for
it to finish before starting the next.

```powershell
py -3.12 -m venv .venv
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

## What you should see

The last command prints a line ending in something like:

```
Uvicorn running on http://127.0.0.1:8909
```

Now open your web browser and go to **http://127.0.0.1:8909**

With the FM9 switched on and plugged in by USB, the link indicator at the top
of the page turns green and names your preset. That is it: you are running.

## Using it again tomorrow

You only do steps 1 to 4 once. After that:

1. Open the `ToneCommand-main` folder.
2. Shift + right-click, **Open PowerShell window here**.
3. Type the last line only:

```powershell
.venv\Scripts\tonecommand
```

4. Go to **http://127.0.0.1:8909** in your browser.

## If something goes wrong

**"UnicodeDecodeError: 'charmap' codec can't decode byte ..."** just after
you run the last line
Your copy is older than 1.5.3. Windows reads text files in a different
character set than macOS and Linux, and one of ToneCommand's data files
holds a curly quote it cannot read, so the program stopped before it
started. Download the ZIP again from the green **Code** button (Step 3) and
redo Step 5 in the new folder: current versions read every file as UTF-8 and
this cannot happen. If you would rather not re-download right now, paste this
line into the same terminal window first, then run the last line again:

```powershell
$env:PYTHONUTF8 = "1"
```

That tells Python to read files the way ToneCommand writes them, for that
window only.

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
FM9 or FM3**
For an FM9, check in this order: the unit is switched on; the USB cable goes
from the unit to the computer and is a data cable rather than a charge-only
one; Fractal's driver from Step 2 is installed; and FM9-Edit is **closed**,
because only one program can hold the unit's USB connection at a time. For an
FM3, check the MIDI interface instead: both 5-pin cables are connected the
right way round, and the FM3 card on the Devices page names that interface's
port.

**"Preparing metadata (pyproject.toml) did not run successfully"**, with
**python-rtmidi** and **"Unknown compiler(s)"** in the red text, or
**"requires a different Python"**
Your Python is newer than 3.12. The MIDI library has prebuilt parts for
Python 3.12 and older only; on a newer one Windows tries to compile it and
cannot. Install Python 3.12 from the releases list (Step 1), delete the
`.venv` folder, open a new terminal and run Step 5 again with
`py -3.12 -m venv .venv` as the first line. Nothing else changes.

**"port 8909 is already in use"**
ToneCommand is already running in another window. Use that one, or close it
and start again.

**Anything else**
Open an issue at **https://github.com/monzta1/ToneCommand/issues** and paste
the red text. The exact wording matters, so copy it rather than describing it.

## Notes for later

- For video builds, install ffmpeg with `winget install ffmpeg` instead of
  Homebrew.
- The guided one-click setup for the ChatGPT subscription route is
  Homebrew-based, so it is macOS only. On Windows, either install
  [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) by hand as its
  own documentation directs, or use any key-based service, the Claude CLI, or
  a local model, which need no helper at all.

## Still stuck

Open an issue at **https://github.com/monzta1/ToneCommand/issues** with the
red text pasted in, or say hello in
[the Slack](https://join.slack.com/t/tonecommand/shared_invite/zt-47oosli5y-GMHa93bbD4Qf76X4s1Crfg).
Every Windows report so far has turned into a fix, and the last one turned
into the test job that now runs on every change.
