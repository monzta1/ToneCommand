"""#308: what an FM3 hardware pass (fw 13.00, through a USB MIDI interface)
found, pinned on the simulator.

- the FM3 numbers its presets from 000, the FM9 from 001;
- a preset select is read back and sent once more if it landed elsewhere;
- the REPORT A PROBLEM button falls back to copy and paste for a long report.

The reconnect behaviour is pinned in tests/test_fm3_port_api.py, which has
the port-level rig it needs."""
import sys

sys.argv = ["x"]
import mido
from fastapi.testclient import TestClient

import server
from fm9 import diagnostics
from fm9 import protocol as p
from fm9.device import FM3, FM9, ReadOnlyOut
from fm9.sim import SimFM3, SimFM9


# -- numbering ----------------------------------------------------------------

def test_the_fm3_numbers_presets_from_zero():
    SimFM3()
    assert p.editor_number(0) == 0
    assert p.editor_number(200) == 200
    assert p.SlotName(5, "x").editor == 5
    assert p.slot_label(128) == "128 (wire 128)"


def test_the_fm9_still_numbers_presets_from_one():
    SimFM3()
    SimFM9()            # connecting the FM9 puts its own numbering back
    assert p.editor_number(0) == 1
    assert p.slot_label(158) == "159 (wire 158)"


def test_the_offset_is_declared_by_each_model():
    assert FM9.EDITOR_OFFSET == 1
    assert FM3.EDITOR_OFFSET == 0


def test_a_failed_connect_does_not_renumber():
    """Only a unit that answered sets the numbering: a failed FM3 connect
    must not renumber an FM9 session's presets."""
    import pytest
    from fm9.device import FM9NotFound
    from fm9.sim import SimFM9Core, SimState, _SimIn, _SimOut
    SimFM9()
    # a unit that answers only another model's frames: the FM3 hears nothing
    core = SimFM9Core(SimState(), model=p.MODEL_FM9)
    inp = _SimIn()
    with pytest.raises(FM9NotFound):
        FM3(registry=core.st.reg, ports=(inp, _SimOut(core, inp)))
    assert p.editor_number(0) == 1


def test_offset_refuses_nonsense():
    import pytest
    with pytest.raises(ValueError):
        p.set_editor_offset(2)


# -- preset select --------------------------------------------------------------

def test_fm3_select_above_128_lands_and_sends_bank_before_program():
    dev = SimFM3()
    port = dev.outp.port
    sent, real = [], port.send

    def spy(msg):
        sent.append(msg)
        return real(msg)
    port.send = spy
    got = dev.select_preset(300)
    assert got is not None and got[0] == 300
    chans = [m for m in sent if m.type != "sysex"]
    assert [(m.type, getattr(m, "value", getattr(m, "program", None))) for m in chans] \
        == [("control_change", 2), ("program_change", 44)]


def test_fm3_select_retries_once_when_the_program_change_is_lost():
    dev = SimFM3()
    port = dev.outp.port
    real, dropped = port.send, []

    def lossy(msg):
        # the interface loses the first program change, as a busy or
        # wireless MIDI link can
        if msg.type == "program_change" and not dropped:
            dropped.append(msg)
            return None
        return real(msg)
    port.send = lossy
    got = dev.select_preset(200)
    assert dropped, "the first program change was not sent"
    assert got is not None and got[0] == 200


def test_fm3_select_that_misses_twice_reports_where_it_landed():
    dev = SimFM3()
    start = dev.current_preset()
    port = dev.outp.port
    real = port.send
    port.send = lambda msg: None if msg.type == "program_change" else real(msg)
    got = dev.select_preset(200)
    assert got == start      # the caller compares and reports the mismatch


def test_fm3_select_still_refuses_out_of_range():
    import pytest
    dev = SimFM3()
    with pytest.raises(ValueError):
        dev.select_preset(512)


# -- report link ----------------------------------------------------------------

def test_long_report_falls_back_to_a_bare_link(monkeypatch):
    long_body = "x" * 9000
    monkeypatch.setattr(diagnostics, "package_for_sharing", lambda **k: {
        "title": "Problem report", "body": long_body,
        "url": "https://github.com/monzta1/ToneCommand/issues/new?body=" + long_body,
        "entry_count": 10})
    r = TestClient(server.app).get("/api/diagnostics/share-package")
    d = r.json()
    assert d["too_long"] is True
    assert d["url"] == f"https://github.com/{diagnostics.REPO}/issues/new"
    assert d["body"] == long_body          # the full report is still there to copy


def test_short_report_keeps_the_prefilled_link(monkeypatch):
    url = "https://github.com/monzta1/ToneCommand/issues/new?title=t&body=b"
    monkeypatch.setattr(diagnostics, "package_for_sharing", lambda **k: {
        "title": "t", "body": "b", "url": url, "entry_count": 1})
    d = TestClient(server.app).get("/api/diagnostics/share-package").json()
    assert d["too_long"] is False and d["url"] == url
