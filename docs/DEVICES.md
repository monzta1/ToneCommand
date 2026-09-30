# Supported devices

ToneCommand talks to a device through an adapter, and every adapter declares
what it can actually do rather than assuming. That declaration is not
decoration: the safety layer reads it, and a device that cannot verify a write
is never allowed to report one as verified. So this page is blunt about what each
device can and cannot do today.

When more than one of these is reachable at once, a picker appears in the
header and a build is refused until you say which device it is for.

| Device | Control | State read back | Notes |
|---|---|---|---|
| **Fractal FM9** | Full | From the unit | The reference implementation. Blocks, scenes, cabs, modifiers, stores, preset files |
| **BOSS IR-2** | Full, all 7 parameters | From the unit | Amp voicing, tone stack, ambience. Announces its own knob moves. IR slots listed, not writable |
| **HeadRush** | Rigs and parameters | From the unit | Core-verified. One verification rerun and one acked-too-early defect still open (#33, #166) |
| **IK Multimedia ToneX** | None, by design | Observed | Captures listed, nothing written. The upload path is undecoded (#27) and stays closed |

Wanted next, each with hardware as the only real blocker: Axe-Fx III (#190),
FM3 (#40), AM4 (#41), VP4 (#191), Kemper, Boss ES-5. The picker is
device-agnostic, so an adapter that registers correctly appears in it with no
interface work at all.

## Fractal FM9

Developed and regression-tested on an FM9 Mk II Turbo across firmware 11.x and
12.00. Everything ToneCommand does on an FM9 is edit-buffer only unless you
explicitly whitelist a store slot, and every write is verified by reading the
unit back. The full capability matrix per firmware is in
[SETUP.md](SETUP.md#compatibility), and the protocol record with evidence per
claim is [PROTOCOL.md](PROTOCOL.md).

Other FM9 variants share the model byte and should behave identically but are
untested. Axe-Fx III and FM3 use different model bytes and are not supported
yet.

## BOSS IR-2

Plug it in by USB and it appears. There is nothing to configure, no
environment variable and no port to choose.

ToneCommand controls all seven of the pedal's parameters:

| Parameter | Range |
|---|---|
| AMP | one of CLEAN, TWN, TWEED, DIAMOND, CRUNCH, BRIT, HI-GAIN, SLDN, BROWN, MODDED, RFIER |
| GAIN, BASS, MIDDLE, TREBLE, LEVEL, AMBIENCE | 0 to 127 |

Every write is followed by a read of the same address, and a write whose
read-back disagrees raises instead of reporting success. The pedal clamps an
out-of-range value silently rather than refusing it, which would look like a
successful write to a naive read-back, so ranges are checked before anything is
sent.

The IR-2 is also the most talkative device ToneCommand supports. It announces
every knob turn and footswitch press without being asked, so ToneCommand knows
when you have changed something on the pedal by hand. The FM9 cannot do that.

**What it does not do.** Its twelve IR slots are listed by name, but nothing
writes to them: the IR transfer path is not decoded, so installing an IR
refuses in one line and sends nothing. Use the BOSS IR-2 IR Loader for that.
The pedal has no scenes and no effect blocks, so those refuse too, by
declaration rather than by pretending. It reports no firmware version, so
ToneCommand reports none rather than inventing one.

The protocol was decoded on hardware on 2026-09-29. Frames, addresses,
evidence and the remaining unknowns are recorded in the project's protocol
ledger.

## HeadRush

Contributed by @bschmalz81401 and on `main` since 1.3.0, reachable over the
network rather than USB. Set `TONECOMMAND_HEADRUSH_HOST` to its address. It is
supported and useful, and it is honest about being unfinished: #33 is held open
for one verification rerun and #166 records a real defect, where the device
acknowledges a rig load before the chain has actually been replaced.

## IK Multimedia ToneX

Read-only on purpose. ToneCommand lists what captures are loaded and reports
what the pedal announces over its serial port, and it has no code path that
writes. The capture-upload format is undecoded by anyone (#27), and until it is
proven, install and remove refuse before a frame exists rather than guessing at
a pedal's flash. Load captures with the TONEX Editor.

## Adding a device

An adapter is one class implementing the contract in
[ARCHITECTURE.md](../ARCHITECTURE.md), plus an honest capability declaration, a
parameter registry and a simulator so the suite runs without hardware. The
safety layer is inherited, not reimplemented. Declaring is deny-by-default, so
an unfinished adapter under-promises rather than over-promises, and a thin one
that only reports state is a legitimate contribution rather than a compromise.

If you own a device on the wanted list, comment on its issue and it is yours.
