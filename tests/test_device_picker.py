"""#139: the device picker in the header, rendered from /api/state's device
block; hidden with one device, a pill and popover with two; a build's 409
opens it. The HeadRush side is the simulator (TONECOMMAND_HEADRUSH_SIM=1)."""
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server

PAGE = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.delenv("TONECOMMAND_HEADRUSH_HOST", raising=False)
    monkeypatch.delenv("TONECOMMAND_HEADRUSH_SIM", raising=False)
    return TestClient(server.app)


# -- REQ-002: one device, nothing changes ------------------------------------------

def test_one_device_state_block_and_the_exact_link_text(client):
    s = client.get("/api/state").json()
    assert s["device"] == {"active": "fm9", "label": "Fractal FM9", "selected": "fm9",
                           "available": [{"kind": "fm9", "label": "Fractal FM9"}], "ambiguous": False}
    # the link text is built from the fixed short-name map, never the API label
    assert ("const DEVICE_SHORT = { fm9: 'FM9', headrush: 'HEADRUSH', "
            "ir2: 'IR-2' };") in PAGE
    assert "$('linktext').textContent = `${deviceShort(freshDevice ? s.device : deviceState)} · LINKED`;" in PAGE
    assert "return DEVICE_SHORT[kind] || (kind ? String(kind).toUpperCase() : 'FM9');" in PAGE
    # with one device the pill stays hidden
    assert '<span class="devwrap" id="devwrap" hidden>' in PAGE
    assert "if (!dev || !dev.available || dev.available.length < 2) { wrap.hidden = true; $('devpop').hidden = true; return; }" in PAGE


# -- REQ-001: two devices, the pill and the popover ------------------------------

def test_two_devices_state_block_before_and_after_a_selection(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_HEADRUSH_SIM", "1")
    s = client.get("/api/state").json()
    assert s["device"]["ambiguous"] is True and s["device"]["selected"] is None and s["device"]["active"] == "fm9"
    assert [d["kind"] for d in s["device"]["available"]] == ["fm9", "headrush"]
    r = client.post("/api/device/select", json={"kind": "headrush"})
    assert r.status_code == 200
    s = client.get("/api/state").json()
    assert s["device"]["active"] == "headrush" and s["device"]["label"] == "HeadRush" and s["device"]["ambiguous"] is False
    assert "device" in s  # present whether or not the rig is connected


def test_device_block_rides_on_the_not_connected_answer(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_HEADRUSH_SIM", "1")

    def boom():
        raise server.FM9NotFound("unplugged")
    monkeypatch.setattr(server, "get_fm9", boom)
    s = client.get("/api/state").json()
    assert s["connected"] is False and s["device"]["ambiguous"] is True


def test_page_markup_carries_the_pill_the_popover_and_the_select_call():
    assert '<button class="pill" id="device" title="which device this build is for">DEVICE</button>' in PAGE
    assert '<div class="pop devpop" id="devpop" hidden></div>' in PAGE
    assert "pill.textContent = dev.ambiguous ? 'CHOOSE DEVICE' : (dev.label || deviceShort(dev)).toUpperCase();" in PAGE
    assert "const r = await fetch('/api/device/select', {" in PAGE
    assert "if (!r.ok) { renderDevicePop(d.error || `the server said ${r.status}`); return; }" in PAGE
    assert "' · active'" in PAGE
    # the stale-poll guard: a poll records the generation when it starts and only renders the block if unchanged
    assert "const pollGen = deviceGen;" in PAGE
    assert "const freshDevice = pollGen === deviceGen;" in PAGE
    assert "if (s.device && freshDevice) renderDevice(s.device);" in PAGE
    # the link text is guarded by the same generation: a stale poll renders the link from the fresh selection state
    assert "const gen = ++deviceGen;" in PAGE and "if (gen !== deviceGen) return;" in PAGE
    assert PAGE.index("const pollGen = deviceGen;") < PAGE.index("const r = await fetch('/api/state');")


# -- REQ-003: a build's 409 opens the picker ---------------------------------------

def test_a_build_refused_for_an_ambiguous_device_opens_the_picker(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_HEADRUSH_SIM", "1")
    for route in ("/api/plan", "/api/plan/stream"):
        r = client.post(route, json={"prompt": "a bit more drive"})
        assert r.status_code == 409 and r.json()["ambiguous_device"] == ["fm9", "headrush"], route
    assert "function deviceRefusal(status, body) {" in PAGE
    assert "if (status === 409 && body && body.ambiguous_device) {" in PAGE
    assert "return 'choose a device first';" in PAGE
    # the stream call site reads the 409 body before throwing, and never says 'the server said 409' for it
    assert "throw new Error(deviceRefusal(r.status, body) || (body && body.error) || `the server said ${r.status}`);" in PAGE
    assert "const body = r.ok ? null : await r.json().catch(() => null);" in PAGE
