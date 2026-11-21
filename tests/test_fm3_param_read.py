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


def test_silence_is_reported_as_no_reply_not_read(monkeypatch):
    reg = Registry()
    dev = SimFM3(reg)
    monkeypatch.setattr(pr, "LISTEN", 0.1)
    real_send = dev._send

    def drop_block_reads(frame):
        if frame[5] == p.FN_BULK_READ:
            return                       # the FM3's answer on fw 13.00: nothing
        real_send(frame)
    monkeypatch.setattr(dev, "_send", drop_block_reads)
    lines = pr.run(dev, reg)
    assert lines[-1] == "result: NO REPLY", lines
    assert any("heard: nothing at all" in line for line in lines)
    assert any(line.startswith("blocks that answered: 0 of") for line in lines)


def test_a_refusal_is_shown_with_its_code():
    nack = p.envelope(p.FN_MULTIPURPOSE, [0x1F, 0x08, 0x00])[1:-1]
    lines = pr.describe_heard([(nack[4], len(nack), nack, 0.05)])
    assert "fn 0x64 x1" in lines[0]
    assert any("refusal/ack: for fn 0x1F, code 8" in line for line in lines)


def test_a_reply_lists_what_was_heard():
    reg = Registry()
    dev = SimFM3(reg)
    lines = pr.run(dev, reg)
    assert any("heard: fn 0x74 x1" in line for line in lines), lines
    assert any("reply: head complete" in line for line in lines), lines


class _Msg:
    type = "sysex"

    def __init__(self, data):
        self.data = data


class _ShortReplies:
    """Replays the shape the tester's PC received from an FM3 (fw 13.00,
    2026-11-20): the head cut after the count's low byte, each chunk three
    bytes short, the end frame whole."""

    def __init__(self, eid, words):
        self.sent = []
        head = [0x00, 0x01, 0x74, 0x11, 0x74, *p.encode14(eid), len(words) & 0x7F]
        frames = [head]
        for off in range(0, len(words), 256):
            part = words[off:off + 256]
            body = [0x00, 0x01, 0x74, 0x11, 0x75, *p.encode14(len(part))]
            for w in part:
                body += [w & 0x7F, (w >> 7) & 0x7F, (w >> 14) & 0x03]
            frames.append(body[:-2])          # 8 + 3n would be whole; 3 short
        frames.append([0x00, 0x01, 0x74, 0x11, 0x76, 0x62])
        self.pending = [_Msg(f) for f in frames]
        self.inp = self

    def iter_pending(self):
        out, self.pending = self.pending, []
        return out

    def _drain(self):
        pass

    def _send(self, frame):
        self.sent.append(frame)


def test_short_frames_still_decode_and_the_shortfall_is_reported(monkeypatch):
    monkeypatch.setattr(pr, "LISTEN", 0.2)
    words = list(range(1000, 1576))                 # 576 words, like the amp
    dev = _ShortReplies(58, words)
    vals, burst, heard = pr.capture_read(dev, 58)
    assert burst["head_len"] == 8 and burst["count"] is None
    assert [c[0] for c in burst["chunks"]] == [256, 256, 64]
    assert vals[:255] == words[:255]                # words before the gap are intact
    line = pr.describe_burst(burst)[0]
    assert "head 8 bytes of 10" in line and "chunks declare 576 words" in line
    assert len(heard) == 5
