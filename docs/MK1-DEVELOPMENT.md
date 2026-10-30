# MK1 development in the shared FX3 repository

Current guidance, updated2026-10-28. This supersedes the historical read-only
kit and separate `development/mk1` branch instructions. Existing release ZIPs
remain pinned for reproducibility; they do not track this source branch.
The app identifies itself as **Unofficial FX3**, without the upstream logo.
For this fork, use [our issue tracker](https://github.com/Axelman8/ToneCommand/issues),
not the official ToneCommand support queue. Legal upstream credit/license remain.

This is the MK1 entry in the shared **Unofficial FX3 source branch**, not an
MK1 production release. You can maintain your own fork, edit in VS Code, run
offline tests and initiate your own locally reviewed MK1 experiments. You do
not need Axelman8 to send you a separate test assignment for every change.

## Get the correct source into your own fork

Repository: https://github.com/Axelman8/ToneCommand

Maintained branch: `integration/axefx3-upstream-20261009` (MK1 and MK2 together).
The earlier `development/mk1` branch is a historical starting point, not a
second independently maintained product. Do not use the old read-only test branch,
generic release Source code ZIP, or `server.py` as your MK1 hardware launcher.
Fork the repository using **your own GitHub account**. If GitHub offers it,
clear **Copy the default branch only**. Clone YOUR fork into a NEW directory.
If the branch was not copied, fetch it explicitly from Axelman8:

```powershell
git clone https://github.com/YOUR-ACCOUNT/ToneCommand.git ToneCommand-MK1
cd ToneCommand-MK1
git remote add axelman8 https://github.com/Axelman8/ToneCommand.git
git fetch axelman8 integration/axefx3-upstream-20261009
git switch --create mk1-development FETCH_HEAD
git push --set-upstream origin mk1-development
```

`origin` is your fork; `axelman8` is the shared starting source. Do not replace
or discard changes in an existing checkout to follow these instructions.
Use feature branches for each independent change. Contributions can be sent
back to Axelman8/ToneCommand as small PRs, with
`integration/axefx3-upstream-20261009` as the base.

## Install and open VS Code

Windows 10/11, Git and official **Python 3.12 64-bit** are required. Existing
working Fractal USB drivers are assumed; no driver or firmware is installed.

1. Open the cloned folder in VS Code. No separate workspace download is needed.
2. Run `ToneCommand.cmd install` once, or choose Install in `ToneCommand.cmd`.
   It creates this clone's `.venv`, installs dependencies and runs offline tests.
3. Run `ToneCommand.cmd test` for the shared mandatory and MK1 regression checks.
4. Start `ToneCommand.cmd mk1`, or choose MK1 in the menu. For MK2 use
   `ToneCommand.cmd mk2`, then connect/select MK2 explicitly in the full GUI.
   Only one mode/process may own port 8909 and MIDI at a time. Existing
   `MK1-Development.code-workspace` tasks/debug configuration remain compatible.
5. Use http://127.0.0.1:8909 and select your own AI backend in Settings.
   API-provider usage can cost money. No other installation's keys are copied.
6. For automated coding assistance, follow `AGENTS.md`. If local `kb/` is
   absent, run `.\.venv\Scripts\python.exe -m tools.bootstrap_fx3_kb` once.
   It derives a private local KB from public references and never overwrites
   an existing KB. Add your MK1 evidence locally; never commit private captures.

Unlike the release launcher, this **explicit developer launcher does not need
`MK1-AI-PACKAGE.json`**. Dirty Git checkouts are allowed at startup and clearly
marked MODIFIED. The UI and report identify HEAD, branch, dirty state and a
SHA-256 of public checkout files. This is reproducibility/drift detection,
not a signature, sandbox, or proof that locally edited code is safe.

Dependencies are declared once in `pyproject.toml` (`.[dev]` for tests) and
installed into this checkout's `.venv`. Do not copy environments, keys, settings
or driver/firmware files from another machine. Existing read-only/release ZIP
launchers are retained for their original artifacts, not required for this flow.

For later updates, stop TC normally, commit your own work, fetch the maintained
branch and merge it into your feature branch. Do not reset a dirty checkout.
If you already cloned `development/mk1`, fetch the shared branch into a clean
working tree and merge `axelman8/integration/axefx3-upstream-20261009`; do not
install another ZIP. Keep your own `origin` and feature branches.

The full workspace now distinguishes MK1 000-511 from declared MK2 000-1023
for preset-name scans, explicit navigation and target validation. Unknown
chassis keeps the conservative 512-slot limit. Upper MK2 addressing has offline
coverage but still needs a native read/navigation test before hardware acceptance.
No Store slot is automatically authorized by selecting MK2 or increasing the
capacity: existing allowlists and separate Store confirmation remain mandatory.
Permanent Store above 511 is not released in this change: the existing shared
Store-policy parser still limits authorizable slots to 0-511. It is deliberately
not widened or bypassed here. Upper MK2 Store needs a separate measured FX3
policy/Store contribution; listing/selecting/building in an upper edit buffer
must not be confused with permission or support to save it permanently.

## Your independent development loop

1. Edit and run offline regression tests. Before a commit, also run:

   ```powershell
   $env:TONECOMMAND_SIM='1'
   .\.venv\Scripts\python.exe -m pytest tests/test_device_handle.py tests/test_capability_gates.py tests/test_ui_warning.py tests/test_mk1_development.py tests/test_mk1_ai_trial.py tests/test_mk1_tester.py -q
   ```

2. Stop TC normally with Ctrl+C **before editing or switching branches**.
   Do not enable Uvicorn auto-reload around an open MIDI connection. Startup
   pins the source; a later edit blocks a new plan/SEND. A change during SEND
   stops before the next write and leaves partial edits. No automatic retry,
   restore, preset reload, or continuing the old review.
3. Close Axe-Edit, start your edited source, then explicitly connect.
4. Select your own disposable EMPTY preset and scene 1 on the MK1. Mute your
   external speakers/headphones and keep them muted throughout the build.
5. Type your request, review the AI's choices, confirm target/mute/experimental
   scope, then SEND once. No shared owner slot grant is assumed.
6. Disconnect TC before opening Axe-Edit. Compare grid, model, parameters and
   effect bypass independently. Readback alone does not prove audible behavior.
   Only then audition at low physical volume. No built-in physical limiter.
7. Export the report and record commit, source hash, exact firmware, your own
   test procedure, observed vs expected values and Axe-Edit/listening results.
   Reports exclude prompts, keys, names and raw MIDI. Review anything you share.
   Keep captures/backups/credentials out of Git. Send small focused PRs.

## Starting functionality and remaining work

The starting UI uses the selected real AI backend to design **one scene** from
text: the shared 336-model Axe-Fx III amp catalog, two Factory2 cabinets,
bounded gain/EQ, optional chorus/delay/reverb. The earlier five-model trial
restriction is removed. Model choices remain explicitly experimental on MK1;
catalog equality is not blanket hardware acceptance. Artist/album requests
are interpretations, not exact matches, with no fixed Pink Floyd preference.
Example: "One scene inspired by Pink Floyd's Wish You Were Here, expressive
lead, suitable AMP/CAB, optional subtle chorus, delay and reverb. No NAM."

The candidate write encodings come from measured MK2 FW33 behavior. Their
acceptance on MK1 remains the purpose of this development work. Startup only
admits the exact MK1 FW33 Beta2 firmware-reply fingerprint already reported by
MGuerrero31416; raw version 97.00 alone is not enough. A different firmware
requires fresh read-only evidence and deliberate reviewed code changes, not
selecting MK2 to bypass detection. Never infer global MK1 write support from
this one explicit experiment.

No NAM/User2 installation, User cab selection/import, controllers, Drive/pitch,
multiple scenes, arbitrary chain editing, global/firmware writes or permanent
Store is offered by this developer UI yet. The full MK2 implementation remains
available in the repository for study and incremental porting; it is **not
automatically enabled** on MK1. Extend a feature only with independent native
evidence, output-boundary tests and full-state preservation checks. Do not widen
allowlists or change the shared never-brick guard. No automatic rollback writes.

The fixed effect blocks are placed even if disabled in the requested sound.
The hardware must expose complete expected layouts/inactive modifiers and
tempo NONE for the timing controls, otherwise execution stops. Conservative
levels are not a guarantee of loudness, balance or sound quality. The preset
remains in the edit buffer; if you independently save it on the front panel or
in Axe-Edit, that is your separate permanent-storage decision.
