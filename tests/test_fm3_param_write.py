"""#40: tools/fm3_param_write.py, the first FM3 settings write.

One knob write to one setting of one block, read back, put back, reloaded;
nothing else may reach the FM3's port, and a value of 0 is never sent."""
import importlib.util
from pathlib import Path

import mido
import pytest

from fm9 import protocol as p
from fm9.device import ReadOnly
from fm9.registry import Registry
from fm9.sim import SimFM3

_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fm3_param_write", _root / "tools" / "fm3_param_write.py")
pw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pw)
pw.SETTLE = 0.0


def _sent(dev):
    frames = []
    real = dev.outp.port.send
    dev.outp.port.send = lambda m: (frames.append([0xF0, *m.data, 0xF7]) if m.type == "sysex" else None,
                                    real(m))
    return frames


def _reverb(reg, dev, mix_wire):
    """Set the reverb's word 13 in the stored preset too, so a reload keeps it."""
    st = dev.sim_core.st
    eid = reg.resolve_block("reverb", 1)[1]
    st.buffer["params"][eid][0][13] = mix_wire
    st.presets[st.buffer["number"]] = st.buffer
    st.buffer = st._load(st.buffer["number"])
    return eid


def test_mix_is_written_read_back_and_put_back():
    reg = Registry()
    dev = SimFM3(reg)
    eid = _reverb(reg, dev, 13107)            # 20%, as on the tester's FM3
    lines = pw.run(dev, reg, "REVERB", say=lambda s: None)
    assert lines[-1] == "result: PASS", lines
    assert any(line.startswith("change: sent 30.0%") and line.endswith("PASS") for line in lines), lines
    assert "  moved: word 13 (channel A): 13107 -> 19660" in lines
    assert any(line.startswith("restore: sent 20.0%") and line.endswith("PASS") for line in lines)
    assert dev.sim_core.st.buffer["params"][eid][0][13] == 13107
    assert "after reload, REVERB 1: exactly as at the start" in lines


def test_a_high_mix_steps_down_not_past_the_top():
    reg = Registry()
    dev = SimFM3(reg)
    _reverb(reg, dev, 62258)                  # 95%
    lines = pw.run(dev, reg, "REVERB", say=lambda s: None)
    assert any(line.startswith("change: sent 85.0%") for line in lines), lines


def test_only_the_read_and_the_one_write_reach_the_fm3():
    reg = Registry()
    dev = SimFM3(reg)
    eid = _reverb(reg, dev, 13107)
    frames = _sent(dev)
    pw.run(dev, reg, "REVERB", say=lambda s: None)
    writes = [f for f in frames if f[5] == p.FN_PARAM]
    assert len(writes) == 2
    for f in writes:
        assert tuple(f[6:8]) == p.SUB_SET_CONTINUOUS
        assert p.decode14(f[8], f[9]) == eid and p.decode14(f[10], f[11]) == 13
        assert p.decode_f32_septets(f[12:17]) > 0.0
    assert {f[5] for f in frames} <= {0x1F, 0x13, 0x0D, 0x0E, 0x14, p.FN_PARAM, 0x3C}, \
        sorted({hex(f[5]) for f in frames})


def test_a_mix_of_zero_is_never_written_back():
    reg = Registry()
    dev = SimFM3(reg)
    _reverb(reg, dev, 0)
    frames = _sent(dev)
    lines = pw.run(dev, reg, "REVERB", say=lambda s: None)
    assert any("Mix was 0" in line for line in lines), lines
    assert len([f for f in frames if f[5] == p.FN_PARAM]) == 1


@pytest.mark.parametrize("frame", [
    p.build_set_param_continuous(66, 13, 0.0),           # the zeroed form: a read
    p.build_set_param_continuous(66, 12, 0.5),           # another setting
    p.build_set_param_continuous(67, 13, 0.5),           # another block
    p.build_set_param_discrete(66, 13, 1),               # another write form
    p.build_bulk_read_poll(67),
])
def test_the_window_refuses_every_other_form(frame):
    dev = SimFM3(Registry())
    with pw.one_param_open(dev, 66, 13):
        assert not dev.outp.allows(frame)
        if not p.fm3_allowed(frame):      # since #40 the port itself passes some of these
            with pytest.raises(ReadOnly):
                dev.outp.send(mido.Message("sysex", data=frame[1:-1]))


def test_the_window_itself_does_not_carry_bypass():
    # Bypass is opened for the FM3 elsewhere (PR #320); this window adds nothing for it.
    dev = SimFM3(Registry())
    with pw.one_param_open(dev, 66, 13):
        assert not dev.outp.allows(p.build_set_bypass(66, True))


def test_the_window_closes_after_use():
    dev = SimFM3(Registry())
    with pw.one_param_open(dev, 66, 13):
        assert dev.outp.allows(p.build_set_param_continuous(66, 13, 0.5))
    assert not isinstance(dev.outp, pw.OneParamOut)
    with pytest.raises(ReadOnly):
        dev.outp.send(mido.Message("sysex", data=p.build_set_param_continuous(66, 3, 0.5)[1:-1]))


def test_a_block_that_is_not_allowed_is_refused():
    reg = Registry()
    dev = SimFM3(reg)
    with pytest.raises(SystemExit):
        pw.run(dev, reg, "DISTORT", say=lambda s: None)


def test_a_write_that_lands_on_another_setting_fails_and_says_where():
    # If the FM3 numbered its settings the FM9's way, word 13 would not move.
    reg = Registry()
    dev = SimFM3(reg)
    _reverb(reg, dev, 13107)
    st = dev.sim_core.st
    real = st.set_block_param
    st.set_block_param = lambda eid, pid, wire, ch=None: real(eid, pid + 10, wire, ch)
    lines = pw.run(dev, reg, "REVERB", say=lambda s: None)
    assert lines[-1] == "result: FAIL"
    assert any(line.startswith("  moved: word 23 (channel A)") for line in lines), lines
