"""#40: tools/fm3_knob_map.py finds where a knob turned on the FM3 lives.

It sends only the block read, for one block, and reports the words that
moved between two reads; the knob is turned by the player on the unit."""
import importlib.util
from pathlib import Path

import mido
import pytest

from fm9 import protocol as p
from fm9.device import ReadOnly
from fm9.registry import Registry
from fm9.sim import SimFM3

_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fm3_knob_map", _root / "tools" / "fm3_knob_map.py")
km = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(km)


def _turn(dev, eid, channel, word, value):
    """What the player does on the unit: change one stored value."""
    dev.sim_core.st.buffer["params"][eid][channel][word] = value


def test_a_turned_knob_is_found_by_word_and_channel():
    reg = Registry()
    dev = SimFM3(reg)
    eid = reg.resolve_block("reverb", 1)[1]
    answers = iter(["", "Time", "1.10 sec", "q"])
    said = []

    def ask(prompt):
        a = next(answers)
        if a == "" and not said[-1:] == ["turned"]:
            _turn(dev, eid, 0, 1, 656)
            said.append("turned")
        return a
    lines = km.run(dev, reg, "REVERB", ask=ask, say=lambda s: None)
    assert lines[-1] == "result: MAPPED"
    assert "round 1: Time = 1.10 sec" in lines
    assert any(line.strip().startswith("word 1 (channel A):") and line.strip().endswith("-> 656")
               for line in lines), lines


def test_no_change_is_said_plainly():
    reg = Registry()
    dev = SimFM3(reg)
    answers = iter(["", "q"])
    lines = km.run(dev, reg, "REVERB", ask=lambda _p: next(answers), say=lambda s: None)
    assert "round 1: no change" in lines


def test_only_the_block_read_reaches_the_fm3():
    reg = Registry()
    dev = SimFM3(reg)
    sent = []
    real = dev.outp.port.send
    dev.outp.port.send = lambda m: (sent.append(list(m.data)), real(m))
    answers = iter(["", "q"])
    km.run(dev, reg, "REVERB", ask=lambda _p: next(answers), say=lambda s: None)
    fns = {d[4] for d in sent if len(d) > 4}
    assert p.FN_BULK_READ in fns
    assert fns <= {p.FN_BULK_READ, p.FN_STATUS_DUMP, p.FN_PATCH_NAME}, fns
    with pytest.raises(ReadOnly):
        dev.outp.send(mido.Message("sysex", data=p.build_bulk_read_poll(66)[1:-1]))


def test_a_missing_block_names_the_ones_there():
    reg = Registry()
    dev = SimFM3(reg)
    with pytest.raises(SystemExit) as e:
        km.run(dev, reg, "WAHWAH", ask=lambda _p: "q", say=lambda s: None)
    assert "has no WAHWAH 1" in str(e.value)
