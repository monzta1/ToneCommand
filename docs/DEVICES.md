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
| **BOSS IR-2** | Full, all 7 parameters, plus IR install | From the unit | Amp voicing, tone stack, ambience. Announces its own knob moves. Load your own cab IRs |
| **Fractal FM3** | Not yet connectable | n/a | No MIDI over USB: it needs a USB MIDI interface on its 5-pin MIDI ports, and connecting through one is being built (#221). Unverified on a real FM3 |
| **HeadRush** | Rigs and parameters | From the unit | Core-verified. One verification rerun and one acked-too-early defect still open (#33, #166) |
| **IK Multimedia ToneX** | None, by design | Observed | Captures listed, nothing written. The upload path is undecoded (#27) and stays closed |

Wanted next, each with hardware as the only real blocker: full FM3 control
(#40), Axe-Fx III (#190), AM4 (#41), VP4 (#191), Kemper, Boss ES-5. A device
ToneCommand recognises but cannot drive yet is named when it is plugged in,
with a link to its issue, instead of being silently ignored. The picker is
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
untested. The FM3 is a different case (below); the Axe-Fx III uses a different
model byte and is not supported yet.

## Fractal FM3 (not yet connectable)

**The FM3 does not do MIDI over USB.** Its USB port carries only Fractal's own
channels for FM3-Edit, Fractal-Bot and Cab-Lab; it never appears as a MIDI
device on Windows or macOS, and installing Fractal's USB driver does not
change that ([Fractal wiki: USB](https://wiki.fractalaudio.com/wiki/index.php?title=USB),
[MIDI](https://wiki.fractalaudio.com/wiki/index.php?title=MIDI)). The FM9 is
different: it does MIDI over USB, which is how ToneCommand reaches it.

An FM3 is reached through a USB MIDI interface connected to its 5-pin MIDI IN
and OUT. Choosing that interface for the FM3 in ToneCommand is being built
(#221). Until it ships, ToneCommand cannot reach an FM3, whatever the cable.

What is ready for when it can: ToneCommand addresses the FM3 through the
FM9's own code with the FM3's model byte, and read-only is enforced at its
MIDI port (only Fractal's documented queries plus preset and scene
switching), because the FM3's block and parameter map has only been proven
on an FM9. None of this has run on a real FM3 yet; the model byte comes from
preset files. Full support is #40.

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

### Loading your own IRs

ToneCommand can write a cabinet IR from your own library into the pedal.

The eleven USER slots are not a free list: each one holds the cabinet for one
amp voicing, in order, so installing an IR replaces that amp's speaker.

| Slot | Voicing | | Slot | Voicing | | Slot | Voicing |
|---|---|---|---|---|---|---|---|
| USER 1 | CLEAN | | USER 5 | CRUNCH | | USER 9 | BROWN |
| USER 2 | TWN | | USER 6 | BRIT | | USER 10 | MODDED |
| USER 3 | TWEED | | USER 7 | HI-GAIN | | USER 11 | RFIER |
| USER 4 | DIAMOND | | USER 8 | SLDN | | | |

Because of that, **no slot is writable until you say so.** Set
`TONECOMMAND_IR2_SLOTS` to the slots you are willing to overwrite, for example
`9,10,11`. Asking for a slot that is not on the list tells you which voicing's
cabinet you were about to replace.

Any 16, 24 or 32-bit PCM wav works. It is resampled to 44.1 kHz, truncated to
the 37 ms the pedal holds with a short fade so the cut does not click, and
peak-normalised, because every factory cab peaks at exactly 1.0 and a hotter
one clips inside the pedal. Every sample is read back and compared before the
install reports success.

**The pedal loads its cabinets at power-on**, so a freshly installed IR is not
audible until you unplug the IR-2 and plug it back in. Switching voicings does
not do it. Every install says so in its result, because otherwise it reads as
a failure.

Removing an IR is refused: it would leave that voicing with no speaker at all,
which the pedal's own editor does not offer. Install something else over it.
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
