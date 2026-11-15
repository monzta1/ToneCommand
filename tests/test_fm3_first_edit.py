"""#40: tools/fm3_first_edit.py, the first write to an FM3.

It proved the FM3's bypass and channel writes on hardware (both are now in
the FM3's own allowed set), and it must leave the unit as it found it."""
import importlib.util
from pathlib import Path

import mido
import pytest

from fm9 import protocol as p
from fm9.device import FM3, ReadOnly
from fm9.registry import Registry
from fm9.sim import SimFM3

_spec = importlib.util.spec_from_file_location(
    "fm3_first_edit", Path(__file__).resolve().parent.parent / "tools" / "fm3_first_edit.py")
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


def _sysex(frame):
    return mido.Message("sysex", data=frame[1:-1])


def test_the_test_flips_reads_back_and_leaves_the_unit_as_it_was():
    reg = Registry()
    dev = SimFM3(reg)
    eid = reg.resolve_block("reverb", 1)[1]
    before = dev.get_bypass(eid)
    lines = fe.run(dev, reg)
    assert lines[-1] == "result: PASS", lines
    assert any(line.startswith("change:") and line.endswith("PASS") for line in lines)
    assert any(line.startswith("restore:") and line.endswith("PASS") for line in lines)
    assert dev.get_bypass(eid) == before
    assert isinstance(dev.outp, fe.ReadOnlyOut)     # the plain gate is back


def test_inside_an_opening_other_writes_are_still_refused():
    """Since #40 the FM3's own port lets bypass and channel through; the
    opening adds nothing beyond that, and parameter writes stay refused."""
    reg = Registry()
    dev = SimFM3(reg)
    reverb = reg.resolve_block("reverb", 1)[1]
    with fe.one_bypass_open(dev, reverb):
        dev.outp.send(_sysex(p.build_set_bypass(reverb, True)))
        with pytest.raises(ReadOnly):
            dev.outp.send(_sysex(p.build_set_param_continuous(reverb, 1, 0.5)))
        with pytest.raises(ReadOnly):
            dev.outp.send(mido.Message("control_change", control=7, value=0))


def test_the_gate_closes_even_when_the_write_fails():
    reg = Registry()
    dev = SimFM3(reg)
    reverb = reg.resolve_block("reverb", 1)[1]
    with pytest.raises(RuntimeError):
        with fe.one_bypass_open(dev, reverb):
            raise RuntimeError("boom")
    assert isinstance(dev.outp, fe.ReadOnlyOut)


@pytest.mark.parametrize("name", ["amp", "cab", "input", "output", "volume"])
def test_blocks_that_can_silence_the_rig_are_never_flipped(name):
    reg = Registry()
    dev = SimFM3(reg)
    with pytest.raises(SystemExit):
        fe.choose(reg, dev.status_dump() or [], name)


def test_the_app_allows_bypass_and_channel_and_refuses_the_rest():
    dev = SimFM3(Registry())
    assert dev.set_bypass(66, True) is True                       # #40: proven
    assert dev.set_channel(66, 1) == 1
    with pytest.raises(ReadOnly):
        dev.set_param_wire(66, 1, 0)
    assert FM3.set_param_wire is FM3._refuse and FM3.set_bypass is not FM3._refuse


def test_the_channel_test_moves_a_block_and_puts_it_back():
    reg = Registry()
    dev = SimFM3(reg)
    eid = reg.resolve_block("reverb", 1)[1]
    before = dev.get_channel(eid)
    lines = fe.run(dev, reg, test="channel")
    assert lines[-1] == "result: PASS", lines
    assert any(line.startswith("change:") and line.endswith("PASS") for line in lines)
    assert dev.get_channel(eid) == before
    assert isinstance(dev.outp, fe.ReadOnlyOut)


def test_only_the_documented_writes_can_be_opened():
    dev = SimFM3(Registry())
    with pytest.raises(ValueError):
        with fe.one_write_open(dev, 66, p.FN_STATUS_DUMP):
            pass
    assert isinstance(dev.outp, fe.ReadOnlyOut)


def test_the_channel_test_skips_single_channel_blocks():
    reg = Registry()
    dev = SimFM3(reg)
    blocks = dev.status_dump() or []
    for b in blocks:
        b.channels_supported = 1
    with pytest.raises(SystemExit):
        fe.choose(reg, blocks, "reverb", need_channels=True)
    assert fe.choose(reg, blocks, None, need_channels=True) is None
