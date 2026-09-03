"""Erasing a preset slot.

The second irreversible operation in the product, and unlike the first it
destroys rather than overwrites: a store replaces a preset with the one you are
holding, this replaces it with nothing. There is no undo, no snapshot and no
copy kept anywhere.

An empty slot is not "a preset with no blocks". The FM9 marks one in its NAME
field, `"<EMPTY>\\0"` over the first 8 bytes with the tail of the old name left
as a ghost (finding 14). A slot whose grid is empty but whose name still reads
Vibroverb is not empty to the device, to FM9-Edit, or to first_empty_slot.
"""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import protocol as p, slots as clear_slot
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
BODY = UI.split("</style>")[1]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "0-511")
    return TestClient(server.app)


# --- what is about to be lost, before anything happens --------------------

def test_the_slot_is_described_without_loading_it(client):
    """fn 0x0D answers from flash and leaves the loaded preset alone (finding
    15), so naming what is about to be destroyed costs the owner nothing."""
    with server._fm9 as dev:
        held = dev.current_preset()
        got = clear_slot.describe(dev, 386)
        assert dev.current_preset() == held, "describing a slot loaded it"
    assert got["name"] == "<EMPTY>" and got["empty"] is True


def test_an_already_empty_slot_is_not_erased_again(client):
    with server._fm9 as dev:
        r = clear_slot.clear(dev, 386)
    assert not r["ok"] and "already reads <EMPTY>" in r["detail"]


# --- the gates -------------------------------------------------------------

def test_the_name_must_be_echoed_back(client):
    """Not ceremony. The wire number and the number every screen shows differ
    by one, and a clear aimed one slot off cannot be taken back. Echoing the
    name means the thing being destroyed was actually looked at."""
    r = client.post("/api/clear-slot",
                    json={"slot": 0, "confirm_name": "not what it holds"})
    assert r.status_code == 409
    assert "Nothing was changed" in r.json()["detail"]
    with server._fm9 as dev:
        assert clear_slot.describe(dev, 0)["empty"] is False


def test_the_store_whitelist_is_enforced_and_not_reimplemented(client,
                                                               monkeypatch):
    """A second copy of a safety boundary is a second thing to get wrong, so
    this leans on store_preset's own check."""
    import inspect
    src = inspect.getsource(clear_slot)
    assert "get_store_slots" not in src, "the whitelist must not be re-checked here"
    assert "dev.store_preset(slot)" in src

    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS", "400-401")
    name = clear_slot.describe(server._fm9, 0)["name"]
    r = client.post("/api/clear-slot", json={"slot": 0, "confirm_name": name})
    assert r.status_code == 403
    assert "refused" in r.json()["detail"]


def test_gig_mode_refuses(client):
    client.post("/api/gig", json={"on": True})
    try:
        r = client.post("/api/clear-slot", json={"slot": 0, "confirm_name": "x"})
        assert r.status_code == 423
    finally:
        client.post("/api/gig", json={"on": False})


def test_a_select_that_landed_elsewhere_stops_it(client, monkeypatch):
    """The select decides which preset every write below it edits. A dropped
    program change would leave someone else's preset in the buffer and this
    would then erase THAT one, permanently."""
    dev = server._fm9
    monkeypatch.setattr(dev, "select_preset", lambda n: (n + 1, "somewhere else"))
    with dev:
        r = clear_slot.clear(dev, 0)
    assert not r["ok"]
    assert "never confirmed" in r["detail"]


# --- what it writes --------------------------------------------------------

def test_all_three_parts_are_written(client):
    """Grid, scene names and the marker. A slot with an empty grid and its old
    name is not empty to anything that asks."""
    import inspect
    src = inspect.getsource(clear_slot.clear)
    assert "place_block(c.row + 1, c.col + 1, 0)" in src
    assert "rename_scene(scene, \"\")" in src
    assert "rename_preset(p.EMPTY_SLOT_NAME)" in src


def test_it_is_believed_only_after_a_reload(client):
    """Finding 16: an incomplete write reads healthy immediately, survives a
    store, and is found undone after the preset reloads. An immediate
    read-back races the device's own validation pass."""
    import inspect
    src = inspect.getsource(clear_slot.clear)
    store = src.index("store_preset")
    assert src.index("select_preset(PARK", store) > store, \
        "the verification must reload before reading back"
    assert "reloaded:" in src


def test_a_clear_that_did_not_take_says_the_preset_may_be_damaged(client,
                                                                  monkeypatch):
    """Half-erased is a worse state than either end, and the owner has to be
    told to go and look rather than assured it worked."""
    dev = server._fm9
    with dev:
        monkeypatch.setattr(dev, "store_preset", lambda slot: None)
        r = clear_slot.clear(dev, 0)
    assert not r["ok"]
    assert "may be damaged rather than cleared" in r["detail"]


def test_it_actually_empties_the_slot(client):
    name = clear_slot.describe(server._fm9, 1)["name"]
    r = client.post("/api/clear-slot",
                    json={"slot": 1, "confirm_name": name}).json()
    assert r["ok"], r["detail"]
    assert r["was"] == name
    with server._fm9 as dev:
        after = clear_slot.describe(dev, 1)
    assert after["empty"] is True and after["name"] == p.EMPTY_SLOT_NAME


def test_the_reply_names_what_was_destroyed(client):
    name = clear_slot.describe(server._fm9, 1)["name"]
    r = client.post("/api/clear-slot",
                    json={"slot": 1, "confirm_name": name}).json()
    assert name in r["detail"] and "there is no" in r["detail"]


def test_the_preset_browser_cache_is_dropped(client):
    """One of the names it is holding just stopped being true."""
    src = Path("server.py").read_text()
    fn = src.split("def api_clear_slot(")[1].split("\ndef ")[0]
    assert '_preset_cache["slots"] = None' in fn


# --- what the browser offers ----------------------------------------------

def test_erasing_sits_with_saving_not_somewhere_quieter():
    """Both write to flash. Hiding the more destructive one elsewhere would
    make it feel like less than it is."""
    panel = BODY.split('id="drawer-storage"')[1].split(
        '<div class="drawpane')[0]
    assert 'id="clearslot"' in panel, "erase lives in the Storage drawer"
    assert '<details class="dangerzone">' in panel, \
        "but one deliberate disclosure deeper than storing"
    assert re.search(r"^\s*#clearslot \{", UI.split("<style>")[1], re.M)


def test_it_is_offered_only_for_a_slot_whose_name_was_read():
    """"Erase" over an unknown name is an invitation to destroy something
    nobody looked at."""
    fn = SCRIPT.split("function updateSaveButton()")[1].split("\n}")[0]
    assert "sel.name && sel.empty !== true" in fn
    assert "$('clearslot').disabled = !named;" in fn


def test_it_asks_once_with_the_name_in_the_dialog():
    """The typed-name echo was tried and retired the same evening: it
    refused legitimate attempts over invisible double spaces, then over a
    machine-built title, then got fed the slot number ("just take the
    number and go delete", Moncy, 2026-09-02). One confirmation, carrying
    the name; the page sends the name it DISPLAYED, so the server still
    refuses a slot that changed since it was shown."""
    fn = SCRIPT.split("$('clearslot').onclick")[1].split("\n};")[0]
    assert "window.confirm(" in fn
    assert "window.prompt(" not in fn, "the typing test is retired"
    assert "It holds:" in fn
    assert "cannot be brought back" in fn
    assert "const typed = slot.name;" in fn


# --- renaming --------------------------------------------------------------

def test_a_rename_is_a_flash_write_not_a_text_edit(client):
    """The FM9 keeps the name inside the preset, so changing it means
    selecting the preset, setting the name and storing the whole thing back."""
    import inspect
    src = inspect.getsource(clear_slot.rename)
    assert "dev.select_preset(slot)" in src
    assert "dev.rename_preset(name)" in src
    assert "dev.store_preset(slot)" in src
    # and the select comes first, so the store writes THAT preset back rather
    # than baking in whatever buffer happened to be loaded
    assert src.index("select_preset(slot)") < src.index("store_preset(slot)")


def test_it_renames(client):
    before = clear_slot.describe(server._fm9, 1)["name"]
    r = client.post("/api/rename-slot",
                    json={"slot": 1, "name": "Bassguy Clean"}).json()
    assert r["ok"], r["detail"]
    assert r["was"] == before
    with server._fm9 as dev:
        assert clear_slot.describe(dev, 1)["name"] == "Bassguy Clean"


def test_it_is_verified_after_a_reload_like_everything_else(client):
    import inspect
    src = inspect.getsource(clear_slot.rename)
    assert src.index("select_preset(PARK") > src.index("store_preset(slot)")
    assert "reloaded:" in src


def test_a_name_too_long_is_refused_before_anything_is_sent(client):
    r = client.post("/api/rename-slot",
                    json={"slot": 1, "name": "x" * 33})
    assert r.status_code == 409
    assert "holds 32" in r.json()["detail"]


def test_an_empty_name_is_refused(client):
    r = client.post("/api/rename-slot", json={"slot": 1, "name": "   "})
    assert r.status_code == 409
    assert "needs a name" in r.json()["detail"]


def test_renaming_to_the_same_name_does_not_write(client):
    name = clear_slot.describe(server._fm9, 1)["name"]
    r = client.post("/api/rename-slot", json={"slot": 1, "name": name})
    assert r.status_code == 409
    assert "already called" in r.json()["detail"]


def test_the_planner_prefix_is_not_applied_here(client):
    """run_action forces an FM9AI- prefix on renames it proposes, so a
    tool-created preset is identifiable. A rename the owner typed is theirs."""
    r = client.post("/api/rename-slot",
                    json={"slot": 1, "name": "Lonestar Lead"}).json()
    assert r["name"] == "Lonestar Lead"


def test_gig_mode_refuses_a_rename(client):
    client.post("/api/gig", json={"on": True})
    try:
        r = client.post("/api/rename-slot", json={"slot": 1, "name": "x"})
        assert r.status_code == 423
    finally:
        client.post("/api/gig", json={"on": False})


def test_the_rename_button_needs_both_a_slot_and_a_name():
    fn = SCRIPT.split("function updateSaveButton()")[1].split("\n}")[0]
    assert "$('renameslot').disabled = !named || !$('newname').value.trim();" in fn


def test_the_rename_confirms_and_says_it_writes_to_flash():
    fn = SCRIPT.split("$('renameslot').onclick")[1].split("\n};")[0]
    assert "window.confirm(" in fn
    assert "writes the slot" in fn and "tone is unchanged" in fn


def test_erase_forgives_spacing_and_case_but_never_the_name(client):
    """Two legitimate erases in a row were refused as "not working"
    (2026-09-01): the names on a real unit carry internal double spaces the
    eye cannot see, and machine-built names nobody retypes exactly. The
    safety property is that the destroyed thing was looked at; invisible
    whitespace is not part of that."""
    real = server._fm9.slot_name(1).name
    mangled = "  " + real.upper().replace(" ", "  ") + " "
    r = client.post("/api/clear-slot",
                    json={"slot": 1, "confirm_name": mangled}).json()
    assert r["ok"], r
    wrong = client.post("/api/clear-slot",
                        json={"slot": 2, "confirm_name": "some other name"})
    assert wrong.status_code == 409


def test_an_erase_refusal_is_announced_not_buried():
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    fn = ui.split("$('clearslot').onclick")[1].split("\n};\n")[0]
    assert "ERASE REFUSED" in fn, "a refusal must be announced, not buried"
    assert "ERASED" in fn, "and so must the success"


def test_the_save_panel_tells_flash_and_buffer_apart():
    """An unsaved build on a slot means two true names for one number: what
    flash holds and what the buffer is called. The panel used to print the
    buffer's name as though it were the slot's, directly above a dropdown
    saying otherwise, and the two read as the app contradicting itself
    (reported 2026-09-01). When they differ, both are named with roles."""
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    fn = ui.split("function aimAtLoadedPreset()")[1].split("\n}\n")[0]
    assert "flash !== buffer" in fn
    assert "The slot holds" in fn
    assert "your unsaved edits" in fn


def test_typing_the_slot_number_gets_coached_not_stonewalled(client):
    """A real erase attempt typed "160" for slot 160 (wire 159): the label's
    big leading number is what the eye lands on. That one wrong answer is
    common enough to deserve its own reply naming the actual ask."""
    r = client.post("/api/clear-slot",
                    json={"slot": 159, "confirm_name": "160"})
    assert r.status_code == 409
    d = r.json()["detail"]
    assert "that is the slot number" in d
    assert "type the NAME" in d
    wire_too = client.post("/api/clear-slot",
                           json={"slot": 159, "confirm_name": "159"})
    assert "that is the slot number" in wire_too.json()["detail"]


def test_the_ui_sends_the_name_it_displayed():
    """The server's name check stays as the API contract and as the stale
    display guard; the page satisfies it with the name it showed rather
    than with a typing test."""
    fn = SCRIPT.split("$('clearslot').onclick")[1].split("\n};\n")[0]
    assert "confirm_name: typed" in fn
    assert "const typed = slot.name;" in fn
