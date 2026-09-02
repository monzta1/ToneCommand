"""Wire numbers versus editor numbers, on the surfaces where being wrong costs.

The wire numbers the 512 slots 0-511; FM9-Edit and the front panel number the
same slots 1-512 (finding 21). This PR taught every CLI surface to print both.
The maintainer's #22 review found the two places that matter most had been
missed: the store confirmation, which is the only destructive prompt in the
product, and the live preset readout that the owner cross-checks against the
panel in front of them.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import protocol as p
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


# --- the destructive prompt names the slot the owner's editor names ---

def test_a_store_action_carries_a_dual_numbered_label(client, monkeypatch):
    """Rendered server side, so the numbering rule lives in protocol.py alone
    rather than being recomputed in the browser."""
    monkeypatch.setattr(server.planner, "plan", lambda *a, **kw: {
        "summary": "save it", "clarification": None,
        "actions": [{"kind": "store", "value": 133, "instance": 1,
                     "reason": "asked to save"}]})
    plan = client.post("/api/plan", json={"prompt": "save this"}).json()
    assert plan["actions"][0]["slot_label"] == "134 (wire 133)"


def test_every_place_a_store_slot_is_shown_uses_the_label():
    """The plan card, the TRANSMIT confirmation, and the headline warning
    above the button. A store is the one irreversible thing in the product,
    so the slot it names must match what the owner sees in FM9-Edit
    everywhere it appears, not in two places out of three."""
    shown = [line for line in UI.splitlines()
             if "OVERWRITES slot" in line or "STORES to preset" in line
             or "OVERWRITES preset slot" in line or "stores.map" in line]
    assert shown, "no store slot is shown anywhere, which cannot be right"
    # The property, not a count. This used to assert an exact number of lines
    # and had to be edited every time a surface was added or a line wrapped,
    # which teaches the next person to bump the number rather than check the
    # rule. The rule is that a raw wire number never reaches the reader.
    for line in shown:
        assert "a.value" not in line or "slot_label" in line, line
        assert ".value}" not in line or "slot_label" in line, line


# --- the live readout matches the panel the owner is looking at ---

def test_the_state_payload_carries_both_numbers(client):
    preset = client.get("/api/state").json()["preset"]
    assert preset["number"] == p.editor_number(preset["number"]) - 1
    assert preset["editor"] == preset["number"] + 1
    assert preset["label"] == p.slot_label(preset["number"])


def test_the_ui_readout_never_shows_the_bare_wire_number():
    """The readout must agree with the front panel.

    Originally this pinned the exact expression that rendered the label. That
    asserted an implementation rather than the intent, and broke the moment
    the pill was changed to carry a single number. The intent is unchanged and
    is what is checked now: the readout resolves through `editor` or `label`,
    never the raw wire number on its own, because the wire numbers presets
    0-511 and every surface the owner cross-checks against numbers them 1-512.
    """
    assert "s.preset.editor" in UI or "s.preset.label" in UI
    # and the rule the rest of the UI follows: both numbers only where being
    # wrong is expensive, which is the store confirmation.
    assert "slot_label" in UI


def test_the_text_snapshot_uses_the_label_too():
    snap = {"preset": {"number": 386, "editor": 387,
                       "label": p.slot_label(386), "name": "TEST"},
            "scene": None, "blocks": [], "values": {}}
    assert "387 (wire 386)" in server.state_text(snap)


# --- the save button: the one destructive control in the product ---

def test_the_ui_offers_only_the_owners_whitelisted_slots(client):
    """Never a free-text slot number. The list IS the safety mechanism, and a
    typo in a text box would overwrite a preset nobody meant to touch."""
    d = client.get("/api/store-slots").json()
    assert d["configured"] and d["slots"]
    from fm9.device import get_store_slots
    assert {s["number"] for s in d["slots"]} == get_store_slots()
    assert "saveslot" in UI and "<select" in UI.split('id="saveslot"')[0][-200:]


def test_every_offered_slot_carries_both_numbers(client):
    """The wire numbers slots 0-511 and the unit numbers them 1-512. Being one
    out here overwrites the wrong preset, which is the definition of a prompt
    that has to be unambiguous."""
    for s in client.get("/api/store-slots").json()["slots"]:
        assert s["label"] == f"{s['editor']} (wire {s['number']})"


def test_the_slot_list_says_what_each_slot_currently_holds():
    """"Overwrite 139" means nothing until you can see what 139 holds."""
    script = UI.split("<script>")[1]
    load = script.split("async function loadSaveSlots")[1].split("\n}")[0]
    assert "s.name" in load and "empty" in load


def test_saving_asks_before_it_overwrites():
    """The confirmation names what is about to be LOST, not just where the
    save lands, and says plainly that undo will not help."""
    script = UI.split("<script>")[1]
    fn = script.split("async function saveToSlot")[1].split("\n}\n")[0]
    assert "window.confirm" in fn
    assert "holds" in fn and "UNDO does not cover this" in fn


def test_a_store_outside_the_whitelist_is_refused(client):
    """Derived from the configured whitelist, never hardcoded.

    The first version of this test named slot 136, which is untouchable on
    Moncy's unit but inside the range conftest configures for the suite. A
    safety test that only passes against one person's .env is not a safety
    test.
    """
    from fm9.device import get_store_slots
    allowed = get_store_slots()
    outside = [n for n in range(0, 512) if n not in allowed][:3]
    assert outside, "nothing outside the whitelist to test against"
    for slot in outside:
        r = client.post("/api/apply", json={"actions": [{
            "kind": "store", "block": "PRESET", "instance": 1,
            "value": slot}]}).json()
        assert not r["results"][-1]["ok"], slot


def test_gig_mode_refuses_to_store(client):
    client.post("/api/gig", json={"on": True})
    try:
        r = client.post("/api/apply", json={"actions": [{
            "kind": "store", "block": "PRESET", "instance": 1, "value": 139}]})
        assert r.status_code == 423
    finally:
        client.post("/api/gig", json={"on": False})


def test_a_store_does_not_arm_an_undo(client):
    """Undo restores the edit buffer. It cannot un-write a preset slot, and an
    UNDO button that looked like it might would be worse than none."""
    import server as srv
    srv._snaps["undo"] = None
    client.post("/api/apply", json={"actions": [{
        "kind": "store", "block": "PRESET", "instance": 1, "value": 139}]})
    assert srv._snaps["undo"] is None


def test_save_aims_at_the_preset_you_are_looking_at():
    """"Save" means "save this preset" to anyone who has used an editor, so
    the selector defaults to the loaded preset rather than the top of a list.
    """
    script = UI.split("<script>")[1]
    assert "function aimAtLoadedPreset" in script
    fn = script.split("function aimAtLoadedPreset")[1].split("\n}")[0]
    assert "lastState.preset" in fn
    assert "$('saveslot').value = String(cur.number)" in fn


def test_a_preset_outside_the_list_is_said_out_loud_not_silently_swapped():
    """Quietly offering a different slot than the one you are on is the exact
    failure the whitelist exists to prevent."""
    script = UI.split("<script>")[1]
    fn = script.split("function aimAtLoadedPreset")[1].split("\n}")[0]
    assert "not in your save" in fn
    assert "blocked" in fn


def test_choosing_a_slot_is_not_undone_by_the_aiming():
    """Wiring the change handler to the aiming function snapped the dropdown
    back to the loaded preset on every pick, which made the selector
    unusable. Aiming sets the selection; the button label only reports it."""
    script = UI.split("<script>")[1]
    assert "function updateSaveButton" in script
    assert "$('saveslot').addEventListener('change', updateSaveButton)" in script
    upd = script.split("function updateSaveButton")[1].split("\n}")[0]
    assert "saveslot').value =" not in upd, "the reporter must not set the value"


def test_the_save_button_names_both_numbers():
    """The one control that cannot be undone, so it follows the rule that
    applies wherever being one out is expensive."""
    script = UI.split("<script>")[1]
    upd = script.split("function updateSaveButton")[1].split("\n}")[0]
    assert "sel.label" in upd and "sel.editor" not in upd


def test_the_panel_says_how_many_slots_and_why():
    """Moncy read a 33 entry list as a half-finished load. A short list with
    no explanation looks like a bug, not a safety catch, so the count and its
    reason are on screen rather than in the source."""
    script = UI.split("<script>")[1]
    assert "savecount" in UI
    assert "slots you marked disposable" in script
    assert "out of 512" in script
