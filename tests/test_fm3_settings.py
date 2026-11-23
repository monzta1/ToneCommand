"""#40: the FM3 settings measured on a real unit, read and written through
the device handle at the FM3's own parameter ids (fm9/fm3_map.py).

The simulator stores a block's values by index and answers the block read
and knob write by that index, so writing FM3 word 13 and reading word 13
round-trips here the way it did on the tester's FM3."""
import mido
import pytest

from fm9 import fm3_map
from fm9 import protocol as p
from fm9.device import FM3_NOT_MAPPED, ReadOnly, ReadOnlyOut
from fm9.registry import Registry
from fm9.sim import SimFM3


def _wire(dev):
    sent = []
    port = dev.outp.port if isinstance(dev.outp, ReadOnlyOut) else dev.outp
    real = port.send

    def spy(msg):
        if msg.type == "sysex":
            sent.append([0xF0, *msg.data, 0xF7])
        return real(msg)
    port.send = spy
    return sent


@pytest.fixture
def reg():
    return Registry()


@pytest.fixture
def dev(reg):
    d = SimFM3(reg)
    d.settle_scale = 0.0
    return d


def _store(dev, eid, word, wire, channel=0):
    dev.sim_core.st.buffer["params"][eid][channel][word] = wire


# -- the map ----------------------------------------------------------------------------

def test_effect_ids_are_the_registrys_instance_1(reg):
    for family, eid in fm3_map.EFFECT_IDS.items():
        assert reg.effect_id(family, 1) == eid


def test_every_entry_names_a_real_fm9_setting(reg):
    for (family, pid), m in fm3_map.PARAMS.items():
        assert (family, pid) in reg.params, (family, pid)
        assert m.dmin < m.dmax and m.scale in ("linear", "log10")


def test_the_measured_readings_decode_to_the_screen(reg):
    """The tester's raw values against what his FM3's screen showed."""
    measured = [("DISTORT", 11, 55507, 8.47), ("DISTORT", 30, 62323, 9.51),
                ("DISTORT", 1, 45874, -10.0), ("REVERB", 11, 22921, 35.04),
                ("REVERB", 12, 45860, 5018.9), ("REVERB", 12, 22948, 1003.1),
                ("REVERB", 19, 29654, 452.5), ("REVERB", 1, 33881, -28.3),
                ("DELAY", 12, 33445, 8166), ("DELAY", 14, 58784, 79.4),
                ("DELAY", 1, 25689, -40.8)]
    for family, pid, wire, screen in measured:
        m = fm3_map.lookup(family, pid)
        shown = p.normalized_to_display(wire / 65534, m.dmin, m.dmax, m.scale)
        assert abs(shown - screen) <= max(0.06, abs(screen) * 0.0005), (family, pid, shown)


def test_only_instance_1_is_mapped():
    assert fm3_map.lookup("REVERB", 0, 1) is not None
    assert fm3_map.lookup("REVERB", 0, 2) is None


# -- reads ------------------------------------------------------------------------------

def test_a_measured_setting_reads_from_the_fm3s_own_place(dev, reg):
    _store(dev, 66, 13, 13107)                    # reverb Mix 20%, as on the tester's unit
    _store(dev, 66, 0, 50000)                     # the FM9's Mix place holds something else
    assert dev.get_param_display(reg.spec("REVERB", 0, 1)) == 20.0


def test_a_short_read_still_finds_channel_b_by_the_declared_stride(dev, reg, monkeypatch):
    """Tony's link lost the last word of each chunk; channels after A must
    still be found by the count the chunks declare, not by what arrived."""
    vals = list(range(100, 100 + 284))           # reverb: 4 x 71
    monkeypatch.setattr(dev, "_fm3_read_block", lambda eid: (vals[:-2], 284))
    monkeypatch.setattr(dev, "get_channel", lambda eid: 1)
    dev._channels[66] = 4
    assert dev.get_param_wire(reg.spec("REVERB", 0, 1)) == 100 + 71 + 13


def test_an_unmeasured_setting_is_not_read_at_all(dev, reg):
    sent = _wire(dev)
    assert dev.get_param_display(reg.spec("REVERB", 15, 1)) is None     # Size
    assert dev.get_param_wire(reg.spec("DISTORT", 10, 1)) is None       # amp model
    assert sent == []


def test_the_fm9_shaped_bulk_read_stays_a_no_send(dev):
    """Callers that index the FM9's map (amp model, cab) get nothing."""
    sent = _wire(dev)
    assert dev.bulk_read(66) is None and sent == []


# -- writes -----------------------------------------------------------------------------

def test_a_measured_setting_is_written_and_read_back(dev, reg):
    _store(dev, 66, 13, 13107)
    sent = _wire(dev)
    r = dev.set_param_display(reg.spec("REVERB", 0, 1), 30.0)
    assert r.ok and r.display_before == 20.0 and r.display_after == 30.0
    assert dev.sim_core.st.buffer["params"][66][0][13] == 19660
    writes = [f for f in sent if f[5] == p.FN_PARAM]
    assert len(writes) == 1
    assert p.decode14(writes[0][8], writes[0][9]) == 66
    assert p.decode14(writes[0][10], writes[0][11]) == 13


def test_a_log_scale_setting_lands(dev, reg):
    r = dev.set_param_display(reg.spec("REVERB", 12, 1), 5000.0)
    assert r.ok, r


@pytest.mark.parametrize("family,pid,value", [
    ("DISTORT", 11, 6.5), ("DISTORT", 30, 3.0), ("DISTORT", 1, -6.0),
    ("DELAY", 12, 450.0), ("DELAY", 14, 35.0), ("REVERB", 11, 2.5),
])
def test_each_kind_of_measured_setting_lands(dev, reg, family, pid, value):
    r = dev.set_param_display(reg.spec(family, pid, 1), value)
    assert r.ok and abs(r.display_after - value) < 0.05, r


def test_an_unmeasured_setting_is_refused_before_the_wire(dev, reg):
    sent = _wire(dev)
    with pytest.raises(ReadOnly, match="not one of the FM3 settings"):
        dev.set_param_display(reg.spec("REVERB", 15, 1), 50.0)
    with pytest.raises(ReadOnly):
        dev.set_param_display(reg.spec("REVERB", 0, 2), 50.0)           # reverb 2
    assert sent == []


def test_a_batch_writes_the_measured_and_names_the_rest(dev, reg):
    res = dev.set_params_batch([(reg.spec("DELAY", 0, 1), 25.0),
                                (reg.spec("DELAY", 20, 1), 100.0)])     # low cut: not measured
    assert res[0].ok
    assert not res[1].ok and "not one of the FM3 settings" in res[1].detail


def test_model_and_exact_wire_writes_stay_refused(dev, reg):
    with pytest.raises(ReadOnly):
        dev.set_param_ordinal(reg.spec("DISTORT", 10, 1), 3)
    with pytest.raises(ReadOnly):
        dev.set_param_wire(reg.spec("REVERB", 0, 1), 100)


def test_the_port_refuses_a_hand_built_write_to_an_unmeasured_place(dev):
    for frame in (p.build_set_param_continuous(66, 3, 0.5),
                  p.build_set_param_continuous(58, 6, 0.5),            # amp model place
                  p.build_set_param_discrete(66, 13, 1)):
        with pytest.raises(ReadOnly):
            dev.outp.send(mido.Message("sysex", data=frame[1:-1]))


def test_the_refusal_names_what_the_fm3_can_change():
    text = FM3_NOT_MAPPED.format(what="Size")
    assert text.startswith("Size is not one of") and "Gain" in text and "#40" in text


# -- the review's gaps (#40) -------------------------------------------------------------

def _chunk(words, declared=None, drop_bytes=0):
    """A 0x75 frame as the FM3 sends it: its own word count, then three
    bytes per word; `drop_bytes` cuts the tail the way the tester's link did."""
    body = [*p.encode14(len(words) if declared is None else declared)]
    for w in words:
        body += [w & 0x7F, (w >> 7) & 0x7F, (w >> 14) & 0x03]
    frame = p.envelope(p.FN_BCAST_BODY, body, p.MODEL_FM3)
    data = frame[1:-1]
    return data[:len(data) - drop_bytes] if drop_bytes else data


class _Replay:
    def __init__(self, frames):
        self.frames = frames

    def iter_pending(self):
        out, self.frames = self.frames, []
        return [mido.Message("sysex", data=f) for f in out]


def _replay(dev, frames, monkeypatch):
    monkeypatch.setattr(dev, "_send", lambda frame: None)
    monkeypatch.setattr(dev, "_drain", lambda: None)
    dev.inp = _Replay(frames)
    dev.FM3_READ_TIMEOUT = 0.3


def test_a_chunk_that_loses_whole_words_keeps_later_values_in_place(dev, monkeypatch):
    head = p.envelope(p.FN_BCAST_HEAD, [*p.encode14(58), *p.encode14(8)], p.MODEL_FM3)[1:-1]
    end = p.envelope(p.FN_BCAST_END, [], p.MODEL_FM3)[1:-1]
    # chunk 1 declares 4 words but loses its last word and checksum (4 bytes)
    frames = [head, _chunk([10, 11, 12, 13], drop_bytes=4), _chunk([20, 21, 22, 23]), end]
    _replay(dev, frames, monkeypatch)
    values, total = dev._fm3_read_block(58)
    assert total == 8
    assert values == [10, 11, 12, None, 20, 21, 22, 23]


def test_tonys_short_chunk_keeps_its_whole_words(dev, monkeypatch):
    head = p.envelope(p.FN_BCAST_HEAD, [*p.encode14(66), *p.encode14(4)], p.MODEL_FM3)[1:-1][:7]
    frames = [head, _chunk([1, 2, 3, 4], drop_bytes=3)]           # 2 bytes of word 4 + checksum
    _replay(dev, frames, monkeypatch)
    values, total = dev._fm3_read_block(66)
    assert (values, total) == ([1, 2, 3, None], 4)


def test_a_lost_value_reads_as_none_not_its_neighbour(dev, reg, monkeypatch):
    vals = [0] * 8 + [None] + [5] * 3
    monkeypatch.setattr(dev, "_fm3_read_block", lambda eid: (vals, len(vals)))
    monkeypatch.setattr(dev, "get_channel", lambda eid: 0)
    dev._channels[70] = 1
    assert dev.get_param_wire(reg.spec("DELAY", 12, 1)) is None    # Time = word 8


def test_a_write_on_channel_b_lands_on_channel_b(dev, reg):
    dev.set_channel(66, 1)
    r = dev.set_param_display(reg.spec("REVERB", 0, 1), 40.0)
    assert r.ok, r
    rows = dev.sim_core.st.buffer["params"][66]
    assert rows[1][13] == round(0.4 * 65534) and rows[0][13] != rows[1][13]


def _with_payload(frame, i, value):
    f = list(frame)
    f[6 + i] = value
    f[-2] = p.checksum(f[1:-2])
    return f


@pytest.mark.parametrize("name,frame", [
    ("value above 1", p.build_set_param_continuous(66, 13, 0.5)[:12]
        + p.encode_f32_septets(1.5) + [0, 0, 0, 0, 0, 0xF7]),
    ("NaN", p.build_set_param_continuous(66, 13, 0.5)[:12]
        + p.encode_f32_septets(float("nan")) + [0, 0, 0, 0, 0, 0xF7]),
    ("high bits in the fifth septet", _with_payload(p.build_set_param_continuous(66, 13, 0.5), 10, 0x10)),
    ("non-zero tail", _with_payload(p.build_set_param_continuous(66, 13, 0.5), 12, 1)),
])
def test_the_gate_refuses_malformed_knob_writes(name, frame):
    f = list(frame)
    f[-2] = p.checksum(f[1:-2])
    assert not p.fm3_allowed(f), name
