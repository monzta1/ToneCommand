"""#40: tools/fm3_param_read.py reads FM3 block settings with the FM9 map.

It may send exactly one form beyond the FM3's allowed set (the block read,
fn 0x1F, for one block, only inside the read), and it must change nothing."""
import importlib.util
from pathlib import Path

import mido
import pytest

from fm9 import protocol as p
from fm9.device import ReadOnly
from fm9.registry import Registry
from fm9.sim import SimFM3

_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fm3_param_read", _root / "tools" / "fm3_param_read.py")
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)


def _sysex(frame):
    return mido.Message("sysex", data=frame[1:-1])


def test_the_read_decodes_blocks_and_changes_nothing():
    reg = Registry()
    dev = SimFM3(reg)
    lines = pr.run(dev, reg)
    assert lines[-1] == "result: READ", lines
    assert any(line.startswith("DISTORT 1") for line in lines)
    assert any(line.strip().startswith("type: ") for line in lines)
    assert any(line.strip().startswith("Gain: ") for line in lines)
    assert isinstance(dev.outp, pr.ReadOnlyOut)


def test_only_that_blocks_read_gets_through_and_only_inside():
    reg = Registry()
    dev = SimFM3(reg)
    amp = reg.resolve_block("amp", 1)[1]
    reverb = reg.resolve_block("reverb", 1)[1]
    with pr.one_read_open(dev, amp):
        dev.outp.send(_sysex(p.build_bulk_read_poll(amp)))               # the one form
        with pytest.raises(ReadOnly):
            dev.outp.send(_sysex(p.build_bulk_read_poll(reverb)))        # another block
        with pytest.raises(ReadOnly):
            dev.outp.send(_sysex(p.build_set_param_continuous(amp, 1, 0.5)))
    with pytest.raises(ReadOnly):
        dev.outp.send(_sysex(p.build_bulk_read_poll(amp)))               # closed again


def test_the_gate_closes_even_when_the_read_fails():
    reg = Registry()
    dev = SimFM3(reg)
    with pytest.raises(RuntimeError):
        with pr.one_read_open(dev, 58):
            raise RuntimeError("boom")
    assert isinstance(dev.outp, pr.ReadOnlyOut)


def test_the_app_still_does_not_read_fm3_settings():
    dev = SimFM3(Registry())
    assert dev.bulk_read(58) is None
    assert not p.fm3_allowed(p.build_bulk_read_poll(58))


def test_the_tool_reads_what_the_app_shows():
    import server
    for fam, pids in pr.READ.items():
        assert server.INTEREST[fam] == pids, fam
    for fam, where in pr.TYPES.items():
        assert server.TYPE_PARAMS[fam] == where, fam
