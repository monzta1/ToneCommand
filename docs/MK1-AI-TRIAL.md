# Experimental MK1 text-to-preset test

**Historical named-package instructions.** Current MK1/MK2 source development
uses one maintained branch and `ToneCommand.cmd`; see
[MK1-DEVELOPMENT.md](MK1-DEVELOPMENT.md). Old release ZIPs retain their original
version, source and limited model scope. Do not install over your working clone.
New test source is branded Unofficial FX3; report fork problems to
[Axelman8/ToneCommand](https://github.com/Axelman8/ToneCommand/issues).

This separate package adds a real request-to-AI workflow, not a fixed preset
script. It uses ToneCommand's selected backend through `fm9.planner.plan` and
the normal per-backend local settings implementation. The AI selects an amp,
Factory cabinet, gain/EQ and enabled chorus/delay/reverb from a constrained
schema. Host code, not the AI, builds and authorizes every MIDI frame.

The new screen follows REQUEST, PLAN, REVIEW, CONFIRM, SEND. Unsupported
requests can produce a question instead of a plan. Include the answer in your
request and generate again. There is no write during AI planning.

## Honest acceptance boundary

Basic MK1 reads and independent editor comparison were reported by the tester.
The exact firmware-reply fingerprint matches the earlier reviewed MK1 report
identifying FW33 Beta2 and Axe-Edit1.15.00. It is not a universal MK1/FW33 decoder.
The candidate write encodings and control layouts were measured on MK2; this
package tests them on MK1 with immediate independent display/bulk/grid readback.
Offline tests and MK2 measurements are not MK1 hardware acceptance. No generic
MK1 production writing capability is enabled by installing this package.

The previous read-only kit, MK2 installation and official upstream adapter are
unchanged. This is a dedicated experimental entry point, not permission to run
the normal server or change chassis declarations to bypass safeguards.

## First use

Download the named MK1 AI trial ZIP and extract to a new writable folder. Use
Windows and Python3.12 64-bit. Run `Install-MK1-AI-Trial.cmd`, then close other
TC processes normally and run `Start-MK1-AI-Trial.cmd`. Only one process owns MIDI.
The browser opens localhost port8909. No driver or firmware is installed.

Choose your own backend in AI SETTINGS. CLI options require an existing signed-in
installation; APIs can be billed by their provider. Keys stay in this new
folder's private settings and are not returned by the server. There is no
automatic or paid provider fallback, account bundle or installer login.

Select an empty disposable preset and scene1 manually on the muted unit. Enter
your permitted number in TC. This device's allowed test preset is your choice;
another owner's MK2 slot permissions do not transfer to your MK1.
Use your normal guitar connection to Input1 and monitoring from Output1. This
trial does not reconfigure global I/O for a different physical setup.

Example request:

> Create one scene inspired by Pink Floyd's Wish You Were Here album for an
> expressive spacious lead. Choose an amp/cab and suitable chorus, delay and
> reverb. No NAM, fuzz, pitch, controllers or permanent storage.

The AI can choose all 336 exact amp names from the shared Axe-Fx III catalog,
and Greenback/Recto Factory2 cabs. The previous five-amp restriction is removed.
This reuses catalog data, not a blanket claim of MK1 hardware acceptance for
every model. Each experimental build still checks the exact MK1 firmware,
selected ordinal, all four Amp channels and complete unrelated observed state.
The designer follows the requested artist/era/role rather than a Pink Floyd
preference. More choices alone do not prove a better sound; compare the actual
settings with Axe-Edit and audition at low volume. Existing schema/level bounds,
one-scene route and unsupported-effect restrictions remain unchanged.
All seven blocks use channelA; effects can be
bypassed. The route is fixed and feed-forward: Input1, Amp1, Cab1, Chorus1,
Delay1, Reverb1, Output1. It is one scene, not an album-wide automatic rig match.
Scenes2-8 are not configured, but shared channelA edits may affect their sound.

Review the actual settings. Before SEND explicitly confirm the target, muted
external monitoring and experimental writes. TC places Output1 and attenuates
it first, voices the detached chain, then connects the input last. Output -18dB,
Amp -12dB, active IR -3dB and FX -1dB are conservative staging, NOT a limiter.
All32 modifiers must be inactive. There is no new controller allocation.

## Stop and recovery rules

Unknown fingerprint, nonempty grid, changed target, unreadable state, unexpected
layout, active modifier, or tempo-synchronised timing stops the test. Review
tokens are single-use and expire. A failed/uncertain write disables further
writes on that connection. Partial edits may remain. There is no automatic
retry, rollback, preset reload, model fallback, Store or flash write.

After verified completion DISCONNECT MIDI, open Axe-Edit, and independently
compare model names, IR selection, active effects, complete routing and levels.
Only then lower physical listening volume, unmute and audition gently. A readback
does not prove bypass transparency, equal loudness, physical safety or tone match.

NAM/User2, IR installation, Send/Return, multi-scene builds, Drive/fuzz, pitch,
controllers, firmware/global writes and permanent storage are excluded. Do not
update firmware simply to make the fingerprint match this trial.

Download the local test report and review it before sharing. It omits prompts,
credentials, preset names, raw SysEx and model payloads. Report whether the
actual audible result and editor comparison passed separately. A failure is
useful evidence, not permission to broaden a guard or restart a partial build.
