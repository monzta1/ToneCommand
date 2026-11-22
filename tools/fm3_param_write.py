#!/usr/bin/env python3
"""The first FM3 settings write (#40): one value changed, read back, put back.

    python tools/fm3_param_write.py              # the reverb's Mix
    python tools/fm3_param_write.py delay        # or the delay's Mix
    TONECOMMAND_FM3_SIM=1 python tools/fm3_param_write.py   # on the simulator

The knob maps (tools/fm3_knob_map.py, 2026-11-22) found where the FM3 keeps
each setting in its block read: the reverb's Mix is word 13 there, where the
FM9 keeps it at parameter 0. This sends the FM9's documented knob write
(fn 0x01 sub 0x52, a value from 0 to 1) to the FM3, addressed by the FM3's
own word number, and reads the whole block back to see which value moved.
That answers the open question (does the FM3 number its settings the way
its block read lays them out?) and is the first proof of an FM3 settings
write.

What it does, in order:
1. reads the loaded preset, its blocks and the whole chosen block;
2. writes one new value to Mix, about 10% away from where it is, and reads
   the whole block again: PASS only if Mix, and nothing else, moved to the
   value sent;
3. writes the old value back and reads again;
4. reloads the preset, which discards the edit buffer, and checks the block
   is exactly as it was at the start. Nothing is ever stored.

The FM3's output stays read-only throughout, except for the block read and
the one knob write, for the one block and the one setting, and only while
each is being sent. A value of exactly 0 is never sent (on the FM9 that form
is a read, not a write). Stop ToneCommand before running this: on Windows
only one program can hold a MIDI port.

At the end it prints a result block to paste back, and saves the same text
to fm3_param_write_result.txt in the current folder.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mido  # noqa: E402

from fm9 import protocol as p  # noqa: E402
from fm9.device import ReadOnly, ReadOnlyOut  # noqa: E402
from fm9.registry import Registry  # noqa: E402
from fm3_first_edit import name_of, open_fm3  # noqa: E402
from fm3_knob_map import read_words  # noqa: E402

#: The only settings this may write: (FM3 word, label), measured by the knob
#: maps on a real FM3 fw 13.00. Both are Mix, 0-100% linear, harmless to move
#: for a moment and easy to see on the screen.
TARGETS = {"REVERB": (13, "Mix"), "DELAY": (0, "Mix")}
#: How far to move it, as a share of the full range.
STEP = 0.10
SETTLE = 0.3
#: Wire values are 0..65534; a read-back within this of the target matches.
TOLERANCE = 2


class OneParamOut:
    """The FM3's read-only output with exactly two more forms let through,
    both for one effect id: the block read (fn 0x1F), and the knob write
    (fn 0x01 sub 0x52) for one parameter, never with a value of 0.
    Everything else still goes to ReadOnlyOut, which refuses any write."""

    def __init__(self, read_only: ReadOnlyOut, effect_id: int, param_id: int):
        self.read_only = read_only
        self.effect_id = effect_id
        self.param_id = param_id

    def _is_read(self, frame: list[int]) -> bool:
        return (len(frame) == 10 and frame[5] == p.FN_BULK_READ
                and p.decode14(frame[6], frame[7]) == self.effect_id)

    def _is_write(self, frame: list[int]) -> bool:
        if len(frame) != 23 or frame[5] != p.FN_PARAM:
            return False
        if tuple(frame[6:8]) != p.SUB_SET_CONTINUOUS or any(frame[17:21]):
            return False
        if p.decode14(frame[8], frame[9]) != self.effect_id:
            return False
        if p.decode14(frame[10], frame[11]) != self.param_id:
            return False
        value = p.decode_f32_septets(frame[12:17])
        return 0.0 < value <= 1.0

    def allows(self, frame: list[int]) -> bool:
        if len(frame) < 10 or frame[0] != 0xF0 or frame[-1] != 0xF7:
            return False
        if tuple(frame[1:4]) != p.MFR or frame[4] not in (p.MODEL_FM9, p.MODEL_FM3):
            return False
        if p.checksum(frame[1:-2]) != frame[-2]:
            return False
        return self._is_read(frame) or self._is_write(frame)

    def send(self, msg):
        if msg.type == "sysex":
            frame = [0xF0, *msg.data, 0xF7]
            if self.allows(frame):
                frame = p.readdress(frame, self.read_only.model)
                self.read_only.port.send(mido.Message("sysex", data=frame[1:-1]))
                return
        self.read_only.send(msg)

    def __getattr__(self, name):
        return getattr(self.read_only, name)


@contextlib.contextmanager
def one_param_open(dev, effect_id: int, param_id: int):
    """Let the two forms through for the length of the block, then put the
    plain read-only output back, whatever happened inside."""
    read_only = dev.outp
    if not isinstance(read_only, ReadOnlyOut):
        raise RuntimeError("expected the FM3's read-only output")
    dev.outp = OneParamOut(read_only, effect_id, param_id)
    try:
        yield
    finally:
        dev.outp = read_only


def _read(dev, eid: int) -> tuple[list[int], int]:
    # read_words opens its own one-block read window.
    return read_words(dev, eid)


def _moved(before: list[int], after: list[int], stride: int) -> list[tuple[int, int, int]]:
    """(index, old, new) for every value that changed."""
    return [(i, before[i], after[i]) for i in range(min(len(before), len(after)))
            if before[i] != after[i]]


def _where(i: int, stride: int) -> str:
    ch = "ABCD"[i // stride] if stride and i // stride < 4 else "?"
    return f"word {i % stride if stride else i} (channel {ch})"


def _pct(wire: int | None) -> str:
    return "not read" if wire is None else f"{wire / 65534 * 100:.1f}%"


def run(dev, reg: Registry, family: str = "REVERB", say=print) -> list[str]:
    """The whole test; returns the result lines. Never stores."""
    if family not in TARGETS:
        raise SystemExit(f"Only {', '.join(f.lower() for f in TARGETS)} can be used for this test.")
    word, label = TARGETS[family]
    out = [f"FM3 first settings write (#40): {family.lower()} {label}"]
    preset = dev.current_preset()
    if preset is None:
        raise SystemExit("The FM3 did not answer. Is ToneCommand stopped, and the "
                         "interface connected?")
    number, pname = preset
    out.append(f"preset: {p.slot_label(number)} {pname!r}")
    blocks = dev.status_dump() or []
    block = next((b for b in blocks
                  if (reg.family_of_effect_id(b.effect_id) or ("", 0)) == (family, 1)), None)
    if block is None:
        raise SystemExit(f"This preset has no {family.lower()} 1. Its blocks: "
                         + ", ".join(name_of(reg, b.effect_id) for b in blocks))
    eid, ch = block.effect_id, block.channel
    chans = max(1, block.channels_supported)
    first, total = _read(dev, eid)
    if not first:
        raise SystemExit("The FM3 sent no values for this block. Is the interface connected?")
    stride = total // chans if chans > 1 else total
    at = ch * stride + word
    if at >= len(first):
        raise SystemExit(f"The block read was too short to reach {label} "
                         f"({len(first)} of {total} values).")
    old = first[at]
    target = old / 65534 + (STEP if old / 65534 <= 1 - STEP - 0.05 else -STEP)
    want = round(target * 65534)
    out.append(f"block: {name_of(reg, eid)} (effect id {eid}), channel {'ABCD'[ch]} of {chans}; "
               f"{label} = FM3 word {word}, before: {_pct(old)} (raw {old})")
    say(f"\nWriting {label} on {name_of(reg, eid)} to {_pct(want)}; watch it on the FM3's screen.")

    def write(value: float) -> str:
        frame = p.build_set_param_continuous(eid, word, value)
        try:
            with one_param_open(dev, eid, word):
                echo = dev._param_echo(frame, eid, word, timeout=1.0)
        except RuntimeError as e:   # the unit's own refusal, in words
            return f"refused by the FM3 ({e})"
        if echo is None:
            return "no echo"
        return f"echo {echo.normalized * 100:.1f}%"

    def settled(expect_at: int) -> list[int]:
        vals: list[int] = []
        for _ in range(4):
            time.sleep(SETTLE)
            vals, _ = _read(dev, eid)
            if at < len(vals) and abs(vals[at] - expect_at) <= TOLERANCE:
                break
        return vals

    # change
    echo = write(target)
    after = settled(want)
    moved = _moved(first, after, stride)
    got = after[at] if at < len(after) else None
    only_mix = [m for m in moved if m[0] != at] == []
    changed = got is not None and abs(got - want) <= TOLERANCE and only_mix
    out.append(f"change: sent {_pct(want)}; {echo}; read back {_pct(got)} -> "
               f"{'PASS' if changed else 'FAIL'}")
    for i, a, b in moved[:8]:
        out.append(f"  moved: {_where(i, stride)}: {a} -> {b}")
    if len(moved) > 8:
        out.append(f"  ... and {len(moved) - 8} more")
    if not moved:
        out.append("  moved: nothing")

    # restore
    if old == 0:
        restored = True
        out.append("restore: Mix was 0, which cannot be written; the reload puts it back")
    else:
        echo = write(old / 65534)
        back = settled(old)
        got = back[at] if at < len(back) else None
        restored = got is not None and abs(got - old) <= TOLERANCE
        out.append(f"restore: sent {_pct(old)}; {echo}; read back {_pct(got)} -> "
                   f"{'PASS' if restored else 'FAIL'}")

    # reload
    reloaded = dev.select_preset(number)
    out.append("reload (discards the edit buffer): "
               f"{p.slot_label(reloaded[0]) if reloaded else 'no answer'}")
    time.sleep(SETTLE)
    final, _ = _read(dev, eid)
    left = _moved(first, final, stride)
    same = bool(final) and not left
    out.append(f"after reload, {name_of(reg, eid)}: "
               f"{'exactly as at the start' if same else f'{len(left)} values differ from the start'}")
    for i, a, b in left[:4]:
        out.append(f"  differs: {_where(i, stride)}: {a} -> {b}")
    out.append(f"result: {'PASS' if changed and restored and same else 'FAIL'}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("block", nargs="?", default="reverb", choices=("reverb", "delay"),
                    help="reverb (default) or delay")
    args = ap.parse_args(argv)
    reg = Registry()
    family = args.block.upper()
    try:
        dev = open_fm3(reg)
    except Exception as e:          # noqa: BLE001  told to the player, in words
        print(f"Could not open the FM3: {e}")
        return 1
    try:
        lines = run(dev, reg, family)
    except ReadOnly as e:
        lines = [f"FM3 first settings write (#40): {args.block}",
                 f"refused before the wire: {e}", "result: FAIL"]
    except (KeyboardInterrupt, EOFError):
        lines = [f"FM3 first settings write (#40): {args.block}",
                 "stopped before the end; reselect the preset on the FM3", "result: STOPPED"]
    finally:
        with contextlib.suppress(Exception):
            dev.close()
    text = "\n".join(lines)
    print("\n----- copy from here -----")
    print(text)
    print("----- to here -----")
    with contextlib.suppress(OSError):
        Path("fm3_param_write_result.txt").write_text(text + "\n", encoding="utf-8")
        print("Also saved to fm3_param_write_result.txt")
    return 0 if lines[-1] == "result: PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
