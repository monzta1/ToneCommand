"""#172: the hardware pass that proves a MIDI backend on the unit. Run here on
the simulator: what the record holds, what makes it incomplete, that the
starting preset is always put back, and how two records are compared."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import server
from fm9 import protocol as p
from fm9.sim import SimFM9
from tests.test_cabs import make_cab
from tests.test_install import make_file
from tools import transport_pass as tp


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.delenv("TONECOMMAND_ALLOW_CAB_READ", raising=False)
    monkeypatch.setenv("TONECOMMAND_CAB_SLOTS", "512-1023")
    preset = tmp_path / "preset.syx"
    preset.write_bytes(make_file(name="Pass Test"))
    cab = tmp_path / "cab.syx"
    cab.write_bytes(make_cab(model=p.MODEL_FM9))
    return preset, cab


def sim():
    dev = SimFM9(server.reg)
    dev.status_dump()
    return dev


#: the name the simulator derives for make_cab's file once installed
CAB_NAME = None


@pytest.fixture(autouse=True)
def _cab_name(files):
    """Learn the name this cab file gets on the simulator, on a throwaway
    unit, so the tests can name it as a player names the cab they hold."""
    global CAB_NAME
    _preset, cab = files
    probe = sim()
    CAB_NAME = probe.install_user_cab_slot(cab.read_bytes(), 600, cab.name).name_after


def test_pass_on_the_simulator_is_complete_and_puts_the_preset_back(files):
    preset, cab = files
    dev = sim()
    start = dev.current_preset()
    rec = tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert tp.problems(rec) == [], tp.problems(rec)
    assert rec["start_preset"] == rec["end_preset"] == list(start)
    assert rec["preset_file"]["name"] == "Pass Test" and rec["preset_file"]["frames"] > 2
    assert rec["capture_after_load"]["preset_name"] != rec["capture_before"]["preset_name"]
    assert rec["cab"]["verified"] and rec["cab"]["slot"] == 522
    json.dumps(rec)                                   # the record serialises as written


def test_pass_never_stores(files, monkeypatch):
    preset, cab = files
    dev = sim()
    monkeypatch.setattr(dev, "store_preset", lambda *a, **k: pytest.fail("the pass stored a preset"))
    tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)


def test_a_cab_slot_outside_the_whitelist_is_refused_before_anything_is_sent(files):
    preset, cab = files
    dev = sim()
    sent = []
    real = dev.outp.send
    dev.outp.send = lambda m: (sent.append(m), real(m))
    with pytest.raises(PermissionError, match="not in TONECOMMAND_CAB_SLOTS"):
        tp.run(dev, server.reg, preset, cab, 5, CAB_NAME)
    assert sent == []


def test_an_unreadable_starting_preset_refuses_before_any_write(files, monkeypatch):
    preset, cab = files
    dev = sim()
    monkeypatch.setattr(dev, "current_preset", lambda: None)
    monkeypatch.setattr(dev, "load_preset_buffer", lambda *a, **k: pytest.fail("wrote with no way back"))
    with pytest.raises(tp.PassError, match="nothing was sent"):
        tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)


def test_a_failure_mid_pass_still_puts_the_preset_back_and_is_incomplete(files, monkeypatch):
    preset, cab = files
    dev = sim()
    start = dev.current_preset()
    def boom(*a, **k):
        raise TimeoutError("the unit stopped acking")
    monkeypatch.setattr(dev, "install_user_cab_slot", boom)
    rec = tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert rec["end_preset"] == list(start)
    assert dev.current_preset() == start
    assert any("the pass stopped: TimeoutError" in x for x in tp.problems(rec))


def test_missing_replies_and_an_unverified_cab_make_a_record_incomplete(files):
    preset, cab = files
    rec = tp.run(sim(), server.reg, preset, cab, 522, CAB_NAME)
    broken = json.loads(json.dumps(rec))
    broken["status"] = []
    broken["cabinet_bulk"] = None
    broken["capture_after_load"]["blocks"][0]["values"] = []
    broken["cab"]["verified"] = False
    found = tp.problems(broken)
    assert "the status dump came back empty" in found
    assert "the CABINET bulk read came back empty" in found
    assert "capture_after_load: 1 block(s) read no values" in found
    assert any(x.startswith("the cab install was not verified") for x in found)


def test_compare_lists_expected_differences_and_fails_on_anything_else(files):
    preset, cab = files
    a = tp.run(sim(), server.reg, preset, cab, 522, CAB_NAME)
    # the simulator's record names whatever binding and Python run the test
    a.update(backend="mido", python="3.12.13")
    b = json.loads(json.dumps(a))
    b.update(backend="supriya", python="3.14.4", seconds=9.9)
    b["cab"]["name_before"] = a["cab"]["name_after"]           # what a second run finds
    unexpected, expected, bad = tp.compare(a, b)
    assert unexpected == [] and bad == []
    assert {e.split(":")[0] for e in expected} == {"/backend", "/python", "/seconds", "/cab/name_before"}
    b["cabinet_bulk"][3] += 1                                  # one byte different
    unexpected, _, _ = tp.compare(a, b)
    assert unexpected == [f"/cabinet_bulk[3]: {a['cabinet_bulk'][3]!r} != {b['cabinet_bulk'][3]!r}"]


# -- REQ-003: packaging, once the pass is green ------------------------------------

def test_packaging_has_no_python_ceiling_and_ci_runs_3_14():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^requires-python = ">=3\.11"$', pyproject, re.M)
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.14"' in ci
    assert "--only-binary=:all:" in ci


def test_a_slot_holding_another_cab_is_refused_before_anything_is_sent(files):
    preset, cab = files
    dev = sim()
    dev.install_user_cab_slot(cab.read_bytes(), 522, cab.name)        # the slot holds this cab now
    sent = []
    real = dev.outp.send
    dev.outp.send = lambda m: (sent.append(m), real(m))
    with pytest.raises(tp.PassError, match="holds .* not 'Someone Else'.*Nothing was sent"):
        tp.run(dev, server.reg, preset, cab, 522, "Someone Else")
    # only the name read went out: no load, no install, no preset change
    assert all(m.data[4] == 0x01 for m in sent), [hex(m.data[4]) for m in sent]


def test_the_slot_s_own_cab_is_re_installed_and_must_read_back_by_name(files):
    preset, cab = files
    dev = sim()
    dev.install_user_cab_slot(cab.read_bytes(), 522, cab.name)
    rec = tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert rec["cab"]["name_before"] == rec["cab"]["name_after"] == CAB_NAME
    assert tp.problems(rec) == []


def test_a_field_the_unit_varies_between_same_backend_runs_does_not_fail_the_compare(files):
    preset, cab = files
    a = dict(tp.run(sim(), server.reg, preset, cab, 522, CAB_NAME), backend="mido")
    base = json.loads(json.dumps(a))
    b = json.loads(json.dumps(a))
    b.update(backend="supriya")
    base["status"][2][1] = not a["status"][2][1]          # the unit flipped a bit between two mido runs
    b["status"][2][1] = not a["status"][2][1]
    unexpected, expected, bad = tp.compare(a, b, base)
    assert unexpected == [] and bad == []
    assert any(e.startswith("/status[2][1]") and "the unit, not the transport" in e for e in expected)
    # without the baseline the same difference fails
    assert tp.compare(a, b)[0] == [f"/status[2][1]: {a['status'][2][1]!r} != {b['status'][2][1]!r}"]
    # a field stable across the baseline still has to match
    b["cabinet_bulk"][0] += 1
    assert tp.compare(a, b, base)[0] == [f"/cabinet_bulk[0]: {a['cabinet_bulk'][0]!r} != {b['cabinet_bulk'][0]!r}"]


def test_the_baseline_must_be_the_same_backend(files):
    preset, cab = files
    a = dict(tp.run(sim(), server.reg, preset, cab, 522, CAB_NAME), backend="mido")
    base = dict(a, backend="supriya")
    assert "the baseline must be a second run on a's backend" in tp.compare(a, dict(a), base)[2]


def test_an_unreadable_cab_slot_name_is_refused_before_anything_is_sent(files, monkeypatch):
    preset, cab = files
    dev = sim()
    monkeypatch.setattr(dev, "read_user_cab_name", lambda slot, timeout=1.5: None)
    sent = []
    real = dev.outp.send
    dev.outp.send = lambda m: (sent.append(m), real(m))
    with pytest.raises(tp.PassError, match="did not answer its name read; nothing was sent"):
        tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert sent == []


def test_a_missing_edit_buffer_name_makes_the_record_incomplete(files):
    preset, cab = files
    rec = tp.run(sim(), server.reg, preset, cab, 522, CAB_NAME)
    for key in ("capture_before", "capture_after_load"):
        broken = json.loads(json.dumps(rec))
        broken[key]["preset_name"] = None
        assert f"{key}: the edit buffer's name was not read" in tp.problems(broken)
    both = json.loads(json.dumps(rec))
    both["capture_before"]["preset_name"] = both["capture_after_load"]["preset_name"] = None
    found = tp.problems(both)
    assert "the edit buffer still shows the starting preset's name after the load" not in found
    assert sum("name was not read" in x for x in found) == 2


def test_a_transient_restore_error_is_retried_and_the_record_is_still_written(files, monkeypatch):
    preset, cab = files
    dev = sim()
    start = dev.current_preset()
    real = dev.select_preset
    calls = []
    def flaky(n):
        calls.append(n)
        if len(calls) == 1:
            raise OSError("the port hiccuped")
        return real(n)
    monkeypatch.setattr(dev, "select_preset", flaky)
    rec = tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert len(calls) == 2 and rec["end_preset"] == list(start)
    assert rec["restore_errors"] == ["OSError: the port hiccuped"]
    assert tp.problems(rec) == []


def test_an_exhausted_restore_returns_an_incomplete_record(files, monkeypatch):
    preset, cab = files
    dev = sim()
    def dead(n):
        raise OSError("the port is gone")
    monkeypatch.setattr(dev, "select_preset", dead)
    rec = tp.run(dev, server.reg, preset, cab, 522, CAB_NAME)
    assert len(rec["restore_errors"]) == 3
    json.dumps(rec)                                   # still a record to write
    assert any("did not end on the preset it started on" in x for x in tp.problems(rec))
