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


def test_a_missed_select_logs_what_was_sent_and_where_it_landed(monkeypatch):
    """#308: presets 128 and up missed on a tester's FM3 behind a wireless
    interface. The report must carry the evidence: the bank (CC0) and
    program sent on each attempt, and where the unit landed."""
    dev = SimFM3()
    start = dev.current_preset()[0]
    port = dev.outp.port
    real = port.send
    port.send = lambda msg: None if msg.type == "program_change" else real(msg)
    logged = []
    monkeypatch.setattr(server.diagnostics, "log_error",
                        lambda scope, message, **ctx: logged.append((scope, message, ctx)))
    monkeypatch.setattr(server, "_fm9", dev)
    monkeypatch.setattr(server, "get_fm9", lambda: dev)
    r = TestClient(server.app, base_url="http://127.0.0.1").post(
        "/api/preset", json={"number": 200})
    assert r.status_code == 409, r.text
    scope, message, ctx = logged[-1]
    assert scope == "preset" and "200" in message
    assert [(a["cc0"], a["program"], a["landed"]) for a in ctx["attempts"]] == \
        [(1, 72, start), (1, 72, start)]
    assert [a["gap_ms"] for a in ctx["attempts"]] == [30, 120]


def test_a_select_that_lands_records_one_attempt():
    dev = SimFM3()
    assert dev.select_preset(300)[0] == 300
    assert dev.last_select == [{"cc0": 2, "program": 44, "gap_ms": 30, "landed": 300}]


def test_fm3_select_still_refuses_out_of_range():
    import pytest
    dev = SimFM3()
    with pytest.raises(ValueError):
        dev.select_preset(512)


# -- report link ----------------------------------------------------------------

def test_the_report_link_carries_the_title_only(monkeypatch):
    """#308: GitHub refused a signed-in tester's pre-filled link of about
    5,000 characters, under the old 7,000 limit. The body never rides in the
    link now; the page copies it for pasting, whatever its length."""
    from urllib.parse import parse_qs, urlsplit
    for body in ("b", "x" * 9000):
        monkeypatch.setattr(diagnostics, "package_for_sharing", lambda body=body, **k: {
            "title": "Problem report: fm3 & presets", "body": body,
            "url": "https://github.com/monzta1/ToneCommand/issues/new?body=" + body,
            "entry_count": 10})
        d = TestClient(server.app, base_url="http://127.0.0.1").get(
            "/api/diagnostics/share-package").json()
        parts = urlsplit(d["url"])
        assert f"{parts.netloc}{parts.path}" == f"github.com/{diagnostics.REPO}/issues/new"
        assert parse_qs(parts.query) == {"title": ["Problem report: fm3 & presets"]}
        assert d["body"] == body            # the full report is there to copy
        assert len(d["url"]) < 200


def test_the_scriptless_report_page_links_the_title_only(monkeypatch):
    monkeypatch.setattr(diagnostics, "package_for_sharing", lambda **k: {
        "title": "Problem report", "body": "x" * 9000,
        "url": "https://github.com/monzta1/ToneCommand/issues/new?body=" + "x" * 9000,
        "entry_count": 10})
    page = TestClient(server.app, base_url="http://127.0.0.1").get("/report").text
    assert f"github.com/{diagnostics.REPO}/issues/new?title=Problem%20report\"" in page
    assert "body=" not in page
    assert "paste" in page
