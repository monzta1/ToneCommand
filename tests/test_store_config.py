"""Store whitelist configuration behavior."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from fm9.device import get_store_slots
from fm9.sim import SimFM9


def test_parse_range(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133-148")
    assert get_store_slots() == set(range(133, 149))


def test_parse_mixed(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "5, 140, 150-152")
    assert get_store_slots() == {5, 140, 150, 151, 152}


def test_garbage_and_out_of_range_ignored(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "abc, 600, 140")
    assert get_store_slots() == {140}


def test_unconfigured_disables_store(monkeypatch, tmp_path):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "")
    import fm9.device as device
    monkeypatch.setattr(device, "Path", lambda *a: tmp_path / "nope")
    fm9 = SimFM9()
    with pytest.raises(PermissionError, match="disabled"):
        fm9.store_preset(133)


def test_configured_slot_allowed(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133-148")
    fm9 = SimFM9()
    fm9.status_dump()
    assert fm9.store_preset(140)


def test_outside_configured_refused(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133-148")
    fm9 = SimFM9()
    with pytest.raises(PermissionError, match="refused"):
        fm9.store_preset(509)


# --- a refusal has to describe the rule it is enforcing (#22 review) ---

def test_a_gappy_whitelist_is_not_described_as_a_range(monkeypatch):
    """Naming lowest-to-highest calls every slot in the gap allowed, which
    sends the owner off to fix the wrong thing. Reproduced by the maintainer
    with 133,150-155: refusing 140 printed "store slots are 133-155"."""
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133,150-155")
    fm9 = SimFM9()
    with pytest.raises(PermissionError) as err:
        fm9.store_preset(140)
    msg = str(err.value)
    assert "133-155" not in msg, "the whitelist is not contiguous"
    assert "134 (wire 133)" in msg
    assert "151-156 (wire 150-155)" in msg


def test_the_refused_slot_is_named_in_both_numberings(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133-148")
    fm9 = SimFM9()
    with pytest.raises(PermissionError) as err:
        fm9.store_preset(509)
    assert "510 (wire 509)" in str(err.value)


def test_slot_set_label_collapses_runs():
    from fm9 import protocol as p
    assert p.slot_set_label([133]) == "134 (wire 133)"
    assert p.slot_set_label(range(133, 136)) == "134-136 (wire 133-135)"
    assert p.slot_set_label([5, 133, 134, 135, 200]) == (
        "6 (wire 5), 134-136 (wire 133-135), 201 (wire 200)")


# --- the owner can see and change the boundary from the app ---------------
# It lived only in .env, so the thing protecting 512 presets was invisible from
# the product that enforces it. Moncy authorised a range in conversation, a
# script wrote it to a gitignored file, and six days later he had no way to
# check it and misremembered what it was.

def test_the_spec_reports_where_it_came_from(monkeypatch, tmp_path):
    from fm9 import device
    monkeypatch.delenv("TONECOMMAND_STORE_SLOTS", raising=False)
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(tmp_path / "s.json"))
    assert device.get_store_slots_spec()[1] in (".env", "unset")
    device.set_store_slots_spec("200-205")
    assert device.get_store_slots_spec() == ("200-205", "app")
    assert device.get_store_slots() == set(range(200, 206))


def test_an_environment_pin_cannot_be_widened_from_the_app(monkeypatch, tmp_path):
    """An operator who set the boundary deliberately outside the app must not
    have it moved by a browser."""
    from fm9 import device
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(tmp_path / "s.json"))
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "300-302")
    assert device.get_store_slots_spec() == ("300-302", "environment")
    with pytest.raises(PermissionError):
        device.set_store_slots_spec("0-511")
    assert device.get_store_slots() == {300, 301, 302}


def test_a_corrupt_settings_file_does_not_widen_anything(monkeypatch, tmp_path):
    """Failing open on a safety boundary would be the worst possible default."""
    from fm9 import device
    f = tmp_path / "s.json"
    f.write_text("{ this is not json")
    monkeypatch.delenv("TONECOMMAND_STORE_SLOTS", raising=False)
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(f))
    spec, source = device.get_store_slots_spec()
    assert source != "app", "a corrupt file must not be treated as a choice"


def test_widening_names_what_it_newly_exposes(monkeypatch, tmp_path):
    """"5 more slots" and "the Worship Tutorials packs" are different
    sentences, and only one of them is a warning."""
    import server
    from fastapi.testclient import TestClient
    monkeypatch.delenv("TONECOMMAND_STORE_SLOTS", raising=False)
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(tmp_path / "s.json"))
    c = TestClient(server.app)
    c.post("/api/store-slots", json={"spec": "200-201"})
    d = c.post("/api/store-slots", json={"spec": "200-205"}).json()
    assert [s["label"] for s in d["newly_exposed"]] == [
        f"{n + 1} (wire {n})" for n in range(202, 206)]
    assert d["count"] == 6


def test_narrowing_reports_what_it_took_back(monkeypatch, tmp_path):
    import server
    from fastapi.testclient import TestClient
    monkeypatch.delenv("TONECOMMAND_STORE_SLOTS", raising=False)
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(tmp_path / "s.json"))
    c = TestClient(server.app)
    c.post("/api/store-slots", json={"spec": "200-210"})
    d = c.post("/api/store-slots", json={"spec": "200-205"}).json()
    assert d["removed"] == 5 and not d["newly_exposed"]


def test_the_settings_panel_shows_the_boundary_and_its_source():
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    assert 'data-label="SAFETY &middot; ALLOWED STORE SLOTS"' in ui, \
        "the store whitelist lives under Settings > Safety" 
    assert 'id="slotspec"' in ui and 'id="slotsrc"' in ui
    script = ui.split("<script>")[1]
    assert "not set in the app" in script and "pinned by the" in script


def test_a_widening_can_be_previewed_without_happening(monkeypatch, tmp_path):
    """The first version applied and then reported, so by the time you read
    what you had exposed, you had exposed it. That is backwards for the one
    control governing every preset on the unit, and it bit during development:
    a probe left the boundary at 1-511 with the owner's untouchable packs
    inside it.
    """
    import server
    from fastapi.testclient import TestClient
    from fm9 import device
    monkeypatch.delenv("TONECOMMAND_STORE_SLOTS", raising=False)
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE", str(tmp_path / "s.json"))
    c = TestClient(server.app)
    c.post("/api/store-slots", json={"spec": "200-205"})
    before = device.get_store_slots()

    d = c.post("/api/store-slots", json={"spec": "0-511", "preview": True}).json()
    assert d["preview"] is True and d["count"] == 512
    assert len(d["newly_exposed"]) == 512 - len(before)
    assert device.get_store_slots() == before, "a preview must not write"


def test_the_ui_asks_before_it_widens():
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    fn = ui.split("<script>")[1].split("async function saveSlotSpec")[1].split("\n}\n")[0]
    assert "preview: true" in fn
    assert "window.confirm" in fn
    assert fn.index("preview: true") < fn.index("window.confirm"), \
        "the preview has to come before the question, or the question is theatre"
    assert "Newly at risk" in fn


def test_the_examples_only_fill_the_box():
    """An example that silently moved the boundary would be the worst kind of
    shortcut on this particular control."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    script = ui.split("<script>")[1]
    handler = script.split("document.querySelectorAll('.eg')")[1].split("});")[0]
    assert "$('slotspec').value = b.dataset.eg" in handler
    assert "fetch(" not in handler and "saveSlotSpec" not in handler


def test_a_landed_store_corrects_the_preset_name_cache(monkeypatch):
    """Caught live on 2026-09-01: a plan stored a Metallica build over slot
    159 and the preset dropdown went on offering the overwritten preset's
    name as though it were still there. The store result carries the slot's
    new name, so the cache entry is corrected in place, with no rescan."""
    from fastapi.testclient import TestClient
    import server

    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "133-160")
    sim = SimFM9(server.reg)
    monkeypatch.setattr(server, "_fm9", sim)
    monkeypatch.setitem(server._preset_cache, "slots", [
        {"number": 140, "editor": 141, "label": "140 (FM9-Edit 141)",
         "name": "Old Blackface", "empty": False}])
    r = TestClient(server.app).post("/api/apply", json={"actions": [
        {"kind": "store", "block": "PRESET", "instance": 1, "value": 140}]})
    res = r.json()["results"][0]
    assert res["ok"], res
    row = server._preset_cache["slots"][0]
    assert row["name"] != "Old Blackface"
    assert row["name"] == sim.current_preset()[1]


def test_the_page_refreshes_its_slot_lists_after_a_stored_transmit():
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    fn = ui.split("async function apply()")[1].split("\n}\n")[0]
    at = fn.index("if (stored.length) {")
    block = fn[at:at + 220]
    assert "loadPresets(false)" in block
    assert "loadSaveSlots(false)" in block
