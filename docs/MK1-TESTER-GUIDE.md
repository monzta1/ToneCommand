# Unofficial ToneCommand Axe-Fx III Mark I evaluation

**Historical read-only kit instructions.** For current experimental MK1 source
development, use [MK1-DEVELOPMENT.md](MK1-DEVELOPMENT.md). This guide describes
the named immutable test package below; its launcher's write restrictions
remain intentional. Do not enable writes by bypassing this read-only launcher.

This Windows test package contains the current FX3 source application plus a
dedicated **read-only MK1 test launcher**. Its purpose is to establish MK1
communication and collect evidence before enabling writes. It is not an
official ToneCommand or Fractal Audio release, and it does not yet build usable
presets on MK1. Please do not interpret a successful connection as write support.

Package version: **1.5.16-fx3.3-mk1-test.2**. TC's underlying package version is
1.5.16. The exact source commit and source-file hashes are in `MK1-PACKAGE.json`.
The hardware comparison previously performed on MK2 does not prove MK1 behavior.

## What you need

- Windows 10 or 11, 64-bit, and an Axe-Fx III Mark I connected by USB.
- [Python 3.12, 64-bit Windows installer](https://www.python.org/downloads/release/python-31210/).
  Select the Python launcher during installation. Python 3.14 is not a substitute
  for this measured Windows MIDI runtime.
- A working official Fractal USB driver and compatible Axe-Edit installation.
  Obtain them from the [official downloads page](https://www.fractalaudio.com/axe-fx-iii-downloads/).
  This package never installs drivers, changes firmware or asks for administrator access.
- Internet during dependency installation. No AI or TONE3000 account is needed.
- Optional: Visual Studio Code and its Python extension for scripted scenarios.

Record the exact installed firmware, including beta/build information. Do not
write only "latest". The production downloads page and public beta releases can
be different. **Do not update firmware just to run this test.**

## MK1 and MK2 differences that matter here

| Area | Mark I | Mark II | This evaluation |
|---|---|---|---|
| NAM-era FW33 User Cab Bank2 | Replaced by NAM storage | Separate NAM memory retains User2 | No bank, IR or NAM writes, and no MK2 slot-address assumptions |
| Older tested FW32.06 policy | User2 remains a cab bank | User2 remains a cab bank | Still read-only in this package |
| Model and parameter evidence | Requires MK1 validation | Narrow combinations already measured on MK2 | MK2 results never release MK1 writes |
| Preset/scene navigation | Can change sound and volume | Can change sound and volume | Select manually on the muted unit, not through TC |
| CPU, other firmware and other chassis | Need exact unit evidence | Prior MK2 results are scoped | No automatic compatibility or sound-match claim |

The NAM memory distinction is recorded in the first page of the release notes
inside the [official FW33 beta archive](https://www.fractalaudio.com/downloads/firmware-presets/axe-fx-3/33p0/axefxiii_dsp_rel_33p00_beta2.zip).
Do not install that archive as part of this evaluation. A NAM-capable firmware
update can erase MK1 User2 IRs; relevant backups must be handled separately by
the unit owner before any future firmware update.

## First installation

1. Download the named **MK1 Tester ZIP asset**, not GitHub's generic Source code
   ZIP. Extract it completely to a new writable folder such as
   `C:\ToneCommand-MK1-Test`. Avoid Program Files, OneDrive and protected folders.
2. Open `Install-MK1.cmd`. It creates only this folder's `.venv`, installs the
   declared dependencies and runs the offline guard tests. It never opens MIDI.
3. If Python is missing, install the official Python3.12 64-bit distribution,
   then run the installer again. A different existing virtual environment is
   refused. Never delete another application's environment to fix this.
4. Wait for "Setup and offline safety tests passed". A failed test means stop,
   save the error locally and contact the developer before connecting hardware.
5. Preserve any unsaved edits using your normal official workflow before manual
   preset/scene selection. Close any other TC and Axe-Edit normally. Connect the unit, mute your external
   monitoring and run `Start-MK1.cmd`. Leave its console open.
6. The browser opens `http://127.0.0.1:8909/mk1-test`. If it does not, enter that
   exact local URL manually. Press CONNECT MK1 on the English page.
7. Press Ctrl+C in the server console to stop normally. Never start a second
   copy to work around an occupied port.

The CMD shortcuts use a process-only PowerShell execution-policy setting to run
the included scripts; they do not change your machine's permanent policy. Follow
your organization's security rules if scripts are managed centrally.

**Always use Start-MK1.cmd or the MK1 VS Code task. Do not run server.py, the
normal tonecommand command or the normal production launcher for this test.**
The extra output guard belongs to the test entry point, not to every possible
way of running or modifying the included source.

## What you can and cannot use

The English test page connects/disconnects, reads the selected preset/scene,
reads scene names, block status and grid, and collects observations. The current
TC GUI is included for inspection through "Open the current TC interface".
Fixed interface labels and guidance now use English. LANGUAGE imports matching
optional JSON packs without translating preset names, user input or AI replies.
English and a translator template are included, not a full Dutch translation.
See `docs/LANGUAGE-PACKS.md` for downloads and contribution instructions.
Scene/preset selection and preset generation are
disabled. A disabled action or a read-only refusal is expected, not a dead pedal
or a broken unit.

No parameter/model/IR changes, controller assignment, NAM inventory/install,
NAM-memory reads, Store, reamp, audio routing, account sign-in or global MIDI
mapping are enabled. Even MIDI Program Change and Control Change are rejected.
Only the exact basic read requests are permitted at the output port. No guessed
parameter-zero query or alternative opcode is attempted when a read fails.

This is a source evaluation, not a tamper-proof sandbox. Editing the guard or
using another launcher invalidates its read-only evidence. Do not use MK2 as a
workaround: the test profile refuses it.

## Test scenarios

### MK1 01 Offline installation and safety

Keep the unit disconnected. Run the installer and the offline tests. Expected:
the output guard accepts the documented read shapes and refuses SET, bank/PC,
Store, bulk memory, modifiers and NAM traffic. HTTP write requests are refused
even if the TC interface contains the corresponding controls. Record pass/fail.

### MK1 02 Connection and identity

With monitoring muted and Axe-Edit closed, start the test launcher and connect.
Record the exact firmware and Axe-Edit version in the English page. Create a
`baseline` observation. Expected: preset/scene match the unit and `coherent`
is true. Missing fields are reported in `read_errors`; they are not guessed.
An unfamiliar firmware may answer basic reads without becoming write-supported.

### MK1 03 Scene observation

Manually select another scene on the muted unit. Create a `manual-scene-2`
observation and compare its scene number with the hardware. TC must not select
the scene itself. Restore your preferred scene manually. No preset save is needed.

### MK1 04 Independent Axe-Edit comparison

Press DISCONNECT MIDI in the test page. Open Axe-Edit and compare the preset,
scene names, grid and block bypass/channel indicators. Make a screenshot only
if you are comfortable sharing it. Do not change models, routes or memory.
Close Axe-Edit before reconnecting TC. Never use both as MIDI owners together.

### MK1 05 Read-only workflow boundaries

Inspect the normal TC interface. Generating/sending presets, scene navigation,
NAM installation, controller assignment and Store must not become available.
Changing the chassis to MK2 must be refused. Do not try to bypass the guard.
These expected refusals are part of the test result.

### MK1 06 NAM memory review without a TC memory request

After disconnecting TC, inspect the available Cab/NAM banks in Axe-Edit on your
already installed firmware. Record what is visible in your separate checklist.
Do not install, clear or replace a capture, import IRs or update firmware.
No MK2 NAM name/memory request is sent by this package. Targeted protocol
measurement and a separately authorized MK1 write package are later steps.

## VS Code tasks and custom scenarios

Open `MK1-Tester.code-workspace`. Install the recommended Python extension if
needed. Use **Python: Select Interpreter** and select `.venv\Scripts\python.exe`.
Use Terminal > Run Task for install, offline tests, start, observe and export.
The debug configuration is "MK1 read-only TC". Stop its terminal with Ctrl+C.
See [the VS Code environment guide](https://code.visualstudio.com/docs/python/environments).

The original private development knowledge base is not distributed. If you use
a coding assistant that follows `AGENTS.md`, first initialize a local Git
repository in the extracted package (`git init`, requiring Git for Windows),
then run `.venv\Scripts\python.exe -m tools.bootstrap_fx3_kb`. This creates
only local, gitignored knowledge files from public project facts. Do not copy
another developer's private knowledge, credentials or captures. This bootstrap
does not grant hardware write permission.

You can duplicate the provided offline tests or adapt
`packaging/mk1/example_scenario.py`. To keep the package-relative import path,
keep that script in its original folder, or adjust `ROOT` explicitly when
copying it to `notes/`. Modified scenarios should be shared for review before
use with hardware.
Keep fake-port guard tests offline. A hardware scenario must use the running
read-only server and the observation endpoint, never instantiate an unguarded
adapter, open another MIDI owner, change a whitelist or call a writable method.
For example, in the VS Code terminal after the server is connected:

```powershell
.venv\Scripts\python.exe -m tools.mk1_tester observe --label manual-scene-2 --consent-read-only
.venv\Scripts\python.exe packaging/mk1/example_scenario.py --label custom-baseline --confirm-monitoring-muted
.venv\Scripts\python.exe -m tools.mk1_tester export
```

## Reporting and privacy

DOWNLOAD REPORT JSON downloads locally. The export task creates
`test-results/share/MK1-report-<timestamp>.zip`. Nothing is uploaded automatically.
The report contains versions, step labels, read success/coherence, preset/scene
numbers and counts. It omits preset/scene names, local user paths, raw SysEx,
account keys, NAM weights, bank backups and screenshots. Choose step labels and
version descriptions without personal information, and review the JSON first.

Send the reviewed report privately to the developer. Include the completed
scenario checklist and, only by choice, relevant reviewed screenshots. Screenshots
can reveal preset names, serial numbers and account details. Do not paste
credentials, complete banks or proprietary captures into a GitHub issue.

## What happens after the first report

The developer compares MK1 reads with independent Axe-Edit evidence. Missing or
unproven behavior is collected as follow-up work. A later scoped write test needs
the tester's own chosen empty preset/NAM slot, fresh muted-audio confirmation and
separate permanent-storage consent. The MK2 owner's preset321-329 and NAM250-256
permissions do not apply to your unit. No write feature is released merely
because the source code, offline tests or MK2 tests passed.
