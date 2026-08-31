"""With the rig off, half the page is scenery. Take it away.

Moncy's framing: idiot proof it. A slider that cannot move, a scan button that
cannot scan and a scene button that switches nothing are all worse than
absent, because each one invites a click that goes nowhere and teaches you the
tool is broken rather than that the cable is out.

Greying them was the first attempt. Hiding them is simpler and strictly
better: a hidden element is out of the layout AND out of the tab order, so the
bookkeeping that remembered which controls were ALREADY disabled, and the bug
where reconnecting switched those back on, stop existing rather than being
handled.

The other half of the same rule matters just as much: the panels that DO work
offline stay at full brightness. Dimming those would be the same lie in the
other direction, since designing tones, browsing recipes and reviewing what is
queued are all perfectly good with the unit unplugged.
"""
import html
import re
from pathlib import Path

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
SCRIPT = UI.split("<script>")[1]
STYLE = UI.split("<style>")[1].split("</style>")[0]


def _panels(with_class: bool):
    out = []
    for m in re.finditer(r'<div class="console([^"]*)" data-label="([^"]+)"', UI):
        has = "needs-rig" in m.group(1)
        if has == with_class:
            out.append(html.unescape(m.group(2)))
    return out


def test_the_panels_that_need_hardware_are_marked():
    marked = set(_panels(True))
    assert marked == {"SCENES", "SIGNAL CHAIN", "EMPTY SLOT", "AMP & CAB",
                      "GRAPHIC EQ", "EFFECTS", "DYNAMICS & LEVELS",
                      "UNDO / COMPARE", "PRESET HEALTH", "SAVE TO PRESET"}, marked


def test_the_panels_that_work_offline_are_not_dimmed():
    """Planning, recipes and designs are the reason offline mode exists."""
    live = set(_panels(False))
    for panel in ("COMMAND", "TONE RECIPES", "DESIGNED PRESETS", "LOG"):
        assert panel in live, panel


def test_a_panel_that_needs_the_rig_is_removed_not_faded():
    """Out of the layout and out of the tab order in one move."""
    assert "body.rig-off .needs-rig { display: none; }" in STYLE


def test_nothing_is_disabled_by_hand_any_more():
    """That bookkeeping existed only to stop a greyed control being reachable.
    Hiding removes the need, and with it the bug where reconnecting re-enabled
    a control that had been disabled for its own reason."""
    fn = SCRIPT.split("function setRigOff")[1].split("\n}")[0]
    # code, not prose: the comment explaining why this went away naturally
    # mentions the word, and asserting on text rather than behaviour is how a
    # test breaks for no reason
    code = "\n".join(l for l in fn.splitlines() if not l.strip().startswith("//"))
    assert ".disabled" not in code
    assert "wasDisabled" not in SCRIPT
    # the whole switch is now one class toggle
    assert "classList.toggle('rig-off', off)" in code


def test_transmit_is_hidden_even_though_its_panel_works():
    """A plan can be BUILT with the rig off, which is the whole point of the
    designs work. It just cannot be sent."""
    assert "body.rig-off #apply { display: none; }" in STYLE
    assert "COMMAND" in _panels(False)


def test_the_preset_pill_goes_too():
    """There is nothing to switch to."""
    assert "body.rig-off #preset { display: none; }" in STYLE


def test_one_switch_decides_it():
    """So a panel cannot end up dimmed but clickable, or bright but dead."""
    assert SCRIPT.count("function setRigOff") == 1
    assert SCRIPT.count("setRigOff(true)") >= 1
    assert SCRIPT.count("setRigOff(false)") >= 1
    # and it is driven by the poll, which is the only thing that knows
    refresh = SCRIPT.split("async function refresh()")[1].split("\n}\n")[0]
    assert "setRigOff(" in refresh


def test_the_banner_says_what_still_works():
    """"Not connected" alone reads as "nothing works", which is wrong and
    discouraging: everything you build offline is kept and goes out later."""
    banner = UI.split('class="offbanner"')[1].split("</div>")[0].lower()
    assert "not connected" in banner
    # it NAMES what went, so nothing has silently vanished
    assert "hidden" in banner and "scenes" in banner
    # and says what still works, since "not connected" alone reads as
    # "nothing works", which is wrong and discouraging
    assert "design" in banner and "lost" in banner


# --- the one piece of state with no way to correct it --------------------

def test_the_link_pill_is_a_button():
    """A status light you cannot press is useless when the status is wrong,
    and it was wrong in a way nothing could fix: the poll retries, but through
    a MIDI bus view the backend caches for the life of the process, so an FM9
    switched on after the server started stayed invisible however long you
    waited. Restarting the server was the only cure."""
    assert re.search(r'<button class="pill off" id="link"', UI)
    assert "$('link').onclick = reconnect" in SCRIPT


def test_reconnecting_rescans_the_bus_rather_than_just_retrying():
    """Retrying through the same stale client would find the same nothing."""
    import inspect
    import server
    assert hasattr(server, "rescan_midi")
    src = inspect.getsource(server.rescan_midi)
    assert "set_backend" in src and "load=True" in src
    endpoint = inspect.getsource(server.api_reconnect)
    assert "drop_fm9()" in endpoint and "rescan_midi()" in endpoint


def test_a_failed_reconnect_says_why():
    """"Still nothing" is an answer; a silent no-op is not."""
    import inspect
    import server
    src = inspect.getsource(server.api_reconnect)
    assert '"why"' in src
    fn = SCRIPT.split("async function reconnect()")[1].split("\n}\n")[0]
    assert "still no FM9" in fn and "FM9-Edit is not holding the port" in fn


def test_the_poll_does_not_stamp_over_a_reconnect_in_progress():
    """The five second poll rewrites the pill's class, which would wipe the
    busy state mid-look and make the button appear to do nothing."""
    assert SCRIPT.count("classList.contains('busy')") >= 2


# --- an open port is not a connected device ------------------------------

def test_a_device_that_stops_answering_is_reported_as_gone():
    """Pulling the USB leaves the handle valid and every read simply times
    out, so the old snapshot came back with no preset, no scene and no blocks
    and still said connected. The link light stayed green over an empty page.
    """
    import pytest
    import server
    from fm9.device import FM9NotFound
    from fm9.sim import SimFM9

    dev = SimFM9(server.reg)
    with dev:
        dev.current_preset = lambda *a, **k: None     # the cable is out
        with pytest.raises(FM9NotFound, match="stopped answering"):
            server.snapshot(dev)


def test_it_gives_up_before_the_expensive_reads():
    """The rest of a snapshot is eight scene names, a status dump and a bulk
    read per family, each waiting out its own timeout. Finding out slowly
    would freeze the poll for ten seconds an unplugged device does not
    deserve."""
    import inspect
    import server
    src = inspect.getsource(server.snapshot)
    head = src.split("raise FM9NotFound")[0]
    assert "scene_name()" not in head and "status_dump()" not in head


def test_the_state_endpoint_turns_that_into_a_clean_disconnect(monkeypatch):
    """And drops the handle, so the next poll builds a fresh one and can pick
    the device up again the moment it comes back."""
    import server
    from fastapi.testclient import TestClient
    from fm9.device import FM9NotFound
    dropped = {"n": 0}
    monkeypatch.setattr(server, "get_fm9",
                        lambda: (_ for _ in ()).throw(FM9NotFound("gone")))
    monkeypatch.setattr(server, "drop_fm9",
                        lambda: dropped.update(n=dropped["n"] + 1))
    d = TestClient(server.app).get("/api/state").json()
    assert d == {"connected": False}
    assert dropped["n"] == 1


def test_a_reconnect_attempt_rescans_the_bus_first(monkeypatch):
    """Without this the retry is pointless. get_fm9 rebuilds the FM9 object
    when the handle is gone, but the rtmidi backend enumerates through a
    CoreMIDI client it holds for the life of the process, so reconstructing
    against a stale client finds the same nothing however many times it runs.
    """
    import server
    monkeypatch.setattr(server, "_fm9", None)
    monkeypatch.setattr(server, "_last_rescan", {"at": 0.0})
    monkeypatch.delenv("TONECOMMAND_SIM", raising=False)
    calls = {"n": 0}
    monkeypatch.setattr(server, "rescan_midi",
                        lambda: calls.update(n=calls["n"] + 1))
    monkeypatch.setattr(server, "FM9", lambda reg: object())
    server.get_fm9()
    assert calls["n"] == 1, "the bus was not re-enumerated before retrying"


def test_rescanning_is_throttled(monkeypatch):
    """Several endpoints can ask at once while disconnected, and re-enumerating
    several times a second would be waste for no gain."""
    import server
    monkeypatch.setattr(server, "_last_rescan", {"at": 0.0})
    monkeypatch.delenv("TONECOMMAND_SIM", raising=False)
    calls = {"n": 0}
    monkeypatch.setattr(server, "rescan_midi",
                        lambda: calls.update(n=calls["n"] + 1))
    monkeypatch.setattr(server, "FM9", lambda reg: object())
    for _ in range(5):
        monkeypatch.setattr(server, "_fm9", None)
        server.get_fm9()
    assert calls["n"] == 1, "rescanned once per burst, not once per call"
    assert server.RESCAN_EVERY >= 1.0


def test_reconnecting_needs_no_button():
    """The button stays, because a person who has just plugged something in
    wants to press something. But it is a shortcut, not the mechanism."""
    import inspect
    import server
    assert "rescan_midi()" in inspect.getsource(server.get_fm9)
