"""The runtime obeys the contract (#111).

#109 declared `Capabilities` and the seven capability sub-Protocols, and
`server.py` consulted none of it: a route could call any of the sixteen gated
methods on the handle, and a device that had declined the capability found
out on the wire, or worse, one of the 72 broad `except Exception` blocks in
`server.py` swallowed the failure and the route reported a silent success.

Proof here is by SUBSTITUTION, not by a hand-picked case. A sentinel device
that declines every gate and raises if any gated method is reached is
installed in place of the simulator, and every route the app registers is
driven through TestClient from a request table this file checks is complete.
No gated method may fire; every route whose request needs a declined gate
must answer 409 with the refusal JSON naming the gate; every other route must
answer exactly as it did against the plain simulator in a baseline run.

Nothing here touches hardware: the simulator is the only device, and the
network, the planner backends and the AI settings are stubbed or isolated.
"""
from __future__ import annotations

import ast
import base64
import dataclasses
import json
import pathlib
import socket
import sys
import traceback
import urllib.request
import webbrowser

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import server                                                    # noqa: E402
from fm9 import (acquire, ai_settings, describe, designs, diagnostics,  # noqa: E402
                 editbuffer, ir_service, planner, share, updates)
from fm9 import protocol as fp                                   # noqa: E402
from fm9 import recipes as recipebook                            # noqa: E402
from fm9 import sim as fm9sim                                    # noqa: E402
from fm9 import slots as slotops                                 # noqa: E402
from fm9.adapter import CAPABILITY_PROTOCOLS, Capabilities, Topology  # noqa: E402
from fm9.device import FM9                                       # noqa: E402
from fm9.safety import BrickGuardRefusal                         # noqa: E402
from fm9.sim import SimFM9                                       # noqa: E402
from sentinel_device import (DECLINE_ALL, GATED_METHODS,         # noqa: E402
                             SentinelDevice)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SERVER = ROOT / "server.py"
AUDIT = ROOT / "tests" / "data" / "broad_except_audit.json"

# --- the gate matrix, read off the contract rather than typed in ----------

GATE_LABELS = [label for label, _gate, _proto in CAPABILITY_PROTOCOLS]
GATE_MATRIX = {label: sorted(proto.__protocol_attrs__)
               for label, _gate, proto in CAPABILITY_PROTOCOLS}

#: The gates a decline-everything run can be refused on. TopologySelection
#: and SceneSlots are the two the FM9 itself declines, so nothing in
#: server.py calls their methods and no route can be refused on them; and
#: every route that draws cables places a block first, so with everything
#: declined the placement gate answers before the wiring gate is asked. The
#: wiring gate is refused by name on a SELECTED device, in its own test.
REACHABLE_GATES = {"topology>=SELECTED", "has_modifiers", "installs_files",
                   "can_rename"}


def test_gate_matrix_is_derived_from_the_contract():
    """Nine gates, twenty-two methods (#162 added plays_captures with
    four, #198 added has_named_params with two), all
    read off CAPABILITY_PROTOCOLS. The server's own table and the sentinel's
    must be the same derivation."""
    assert GATE_LABELS == ["topology>=SELECTED", "topology==SELECTED",
                           "topology==CONSTRUCTED", "has_modifiers",
                           "installs_files", "can_rename",
                           "composable_scene_slots", "plays_captures",  # #162
                           "has_named_params"]                          # #198
    assert sum(len(v) for v in GATE_MATRIX.values()) == 22
    assert set(GATED_METHODS) == set(server.GATED_METHODS)
    for name, label in GATED_METHODS.items():
        assert server.GATED_METHODS[name][0] == label
    # Every gate declines on the sentinel's declaration.
    for label, gate, _ in CAPABILITY_PROTOCOLS:
        assert gate(DECLINE_ALL) is False, label
    assert DECLINE_ALL.topology is Topology.FIXED, \
        "FIXED is the bottom rung; Topology has no NONE member"


def test_set_tempo_reports_unverified_send_once():
    """REQ-001: no tempo read-back means the result cannot be ok=True."""
    dev = SimFM9(server.Registry())
    sent: list[int] = []
    dev.set_tempo = lambda bpm: sent.append(int(bpm))

    got = server.run_action(dev, server.Action(kind="set_tempo", value=135))

    assert sent == [135]
    assert got == {
        "ok": False,
        "detail": "tempo 135 bpm sent (unverified; no read-back)",
    }


# --- the world around the device, stubbed or isolated ---------------------

STUB_PLAN = {
    "summary": "a stub plan", "clarification": None, "backend": "stub",
    "actions": [{"kind": "set_param", "block": "amp", "instance": 1,
                 "param": "DISTORT_DRIVE", "value": 5.0,
                 "reason": "stubbed"}],
}


def _refuse(name, calls):
    def _f(*a, **kw):
        # Who asked, since a broad except may swallow the refusal itself.
        frames = [f"{fr.filename.rsplit('/', 1)[-1]}:{fr.lineno}"
                  for fr in traceback.extract_stack()[-14:-1]]
        calls.append(f"{name} via {' < '.join(frames)}")
        raise AssertionError(f"{name} must not be reached by any route")
    return _f


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Everything a route can reach that is not the device.

    Files the routes write are moved under tmp_path; the planner backends,
    the share service, the release check, the Gift of Tone catalogue and the
    AI settings probes are stubbed; the network is a tripwire. The MIDI bus
    is never enumerated: the simulator is installed directly.
    """
    return _stub_world(monkeypatch, tmp_path)


def _stub_world(monkeypatch, tmp_path) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(urllib.request, "urlopen", _refuse("urlopen", calls))
    monkeypatch.setattr(socket, "create_connection",
                        _refuse("socket.create_connection", calls))
    monkeypatch.setattr(webbrowser, "open", _refuse("webbrowser.open", calls))

    for var, name in (("TONECOMMAND_DESIGNS_DIR", "designs"),
                      ("TONECOMMAND_RECIPES_DIR", "recipes"),
                      ("TONECOMMAND_OUTBOX", "outbox.json"),
                      ("TONECOMMAND_USER_CABS", "user_cabs.json"),
                      ("TONECOMMAND_AI_SETTINGS", "ai_settings.json")):
        monkeypatch.setenv(var, str(tmp_path / name))
    for var in ("TONECOMMAND_IR_SERVICE", "TONECOMMAND_DEBUG",
                "TONECOMMAND_TONE_DIR", "TONECOMMAND_GIG_MODE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(ir_service, "_config_path",
                        lambda: tmp_path / "ir_service.json")
    # A saved empty URL is the documented OFF state; without it the IR
    # service is DISCOVERED by probing local ports, which is a network call.
    (tmp_path / "ir_service.json").write_text('{"url": ""}\n', encoding="utf-8")
    monkeypatch.setattr(acquire, "tone_dir_path",
                        lambda: tmp_path / "tone_dir.json")
    log = tmp_path / "diag.jsonl"
    real_pkg = diagnostics.package_for_sharing
    monkeypatch.setattr(server.diagnostics, "package_for_sharing",
                        lambda scope=None, limit=10, path=None, note="":
                            real_pkg(scope=scope, limit=limit, path=log,
                                     note=note))
    real_log = diagnostics.log_error
    monkeypatch.setattr(server.diagnostics, "log_error",
                        lambda scope, message, path=None, **kw:
                            real_log(scope, message, path=log, **kw))

    # The MIDI bus: never looked at.
    monkeypatch.setattr(server, "rescan_midi", lambda: None)
    monkeypatch.setattr(server, "_pump_coremidi", lambda: None)
    # The link watcher loops until the client leaves, and TestClient cannot
    # leave an endless stream early. So the bus check answers once (the real
    # first `link` event) and raises on its second look, which ends the
    # stream through the runner's own error path.
    looks = {"n": 0}

    def _port_present_once():
        looks["n"] += 1
        if looks["n"] % 2 == 0:
            raise RuntimeError("test: the bus watcher stops after one look")
        return False
    monkeypatch.setattr(server, "_fm9_port_present", _port_present_once)
    # drop_fm9 would let get_fm9() build a fresh simulator and lose the
    # device under test; nothing in a simulator run can raise FM9NotFound.
    monkeypatch.setattr(server, "drop_fm9", lambda: None)

    # Planner backends.
    monkeypatch.setattr(planner, "plan", lambda *a, **k: json.loads(
        json.dumps(STUB_PLAN)))
    monkeypatch.setattr(planner, "plan_stream", lambda *a, **k: iter(
        [("count", 1), ("plan", json.loads(json.dumps(STUB_PLAN)))]))
    monkeypatch.setattr(planner, "converse", lambda *a, **k: {
        "reply": "stub", "ready": False})
    monkeypatch.setattr(planner, "converse_stream", lambda *a, **k: iter(
        [("text", "stub"), ("done", {"reply": "stub", "ready": False})]))
    monkeypatch.setattr(planner, "repair_action", lambda *a, **k: None)
    monkeypatch.setattr(describe, "read_source", lambda raw, on_stage=None: {
        "text": "a bright clean tone", "kind": "text", "url": None,
        "title": "", "notes": ""})
    monkeypatch.setattr(describe, "_ask", lambda prompt, cancel=None:
                        '{"ops": [{"op": "set_node", "id": "ts", "label": "Klon"}]}')
    monkeypatch.setattr(describe, "extract", lambda text, cancel=None: {
        "found": True, "summary": "bright clean", "stated": [], "vague": [],
        "quotes": []})

    # Services.
    monkeypatch.setattr(recipebook, "fetch_shared", lambda timeout=6.0: ([], None))
    monkeypatch.setattr(share, "fetch_stats", lambda timeout=4.0: ({}, None))
    monkeypatch.setattr(share, "sync", lambda timeout=6.0: {
        "sent": 0, "pending": 0, "endpoint": None})
    monkeypatch.setattr(updates, "latest_release",
                        lambda root, force=False: None)
    monkeypatch.setattr(updates, "run_update", lambda root: {
        "ok": False, "detail": "stubbed: no update runs under test"})
    monkeypatch.setattr(acquire, "search_local", lambda q: [])
    monkeypatch.setattr(acquire, "catalog", lambda: [])
    # The J1 catalog reads the site first (#154); under the tripwire that is
    # an AssertionError out of urlopen, which no route should swallow into a
    # 500. The committed local copy is the honest offline answer.
    from fm9 import gift_of_tone
    monkeypatch.setattr(gift_of_tone, "fetch",
                        lambda timeout=6.0: (gift_of_tone._from_local(), "local", None))
    monkeypatch.setattr(ai_settings, "list_models",
                        lambda backend, base_url="": {
                            "models": [], "source": "stub"})
    monkeypatch.setattr(ai_settings, "setup_guide_state",
                        lambda: {"steps": []})
    monkeypatch.setattr(ai_settings, "endpoint_reachable", lambda base_url: "")
    monkeypatch.setattr(ai_settings, "available_backends", lambda: [])
    monkeypatch.setattr(ai_settings, "local_llm_url",
                        lambda: ai_settings.LOCAL_LLM_DEFAULT_URL)
    return calls


def _reset_server_state():
    """Module-level state the routes carry between requests, back to boot."""
    server._preset_cache["slots"] = None
    server._snaps.update({"undo": None, "a": None, "b": None})
    server._gig_mode["on"] = False
    server._profile["loaded"] = None
    server._install_cache.clear()
    server._plan_revisions.clear()
    server._shared_cache.update({"preset": None, "map": None})
    server._last_snapshot.update({"state": None, "at": None})
    server._synthetic_slots.update({"preset": None, "slots": set()})


def _install(device):
    """Put a device behind get_fm9(). The sentinel is a real second
    implementation, so nothing else in server.py needs to change."""
    _reset_server_state()
    server._fm9 = device
    # A/B restore needs something captured; the simulator's own buffer.
    server._snaps["a"] = editbuffer.capture(server.get_fm9(), server.reg)
    # The two install routes need a parsed file pending. Junk is enough:
    # the gate is checked on the handle before the device parses anything,
    # and the simulator refuses the junk as a bad file without transmitting.
    server._install_cache[JUNK_HASH] = b"not a real preset or cab file"


# --- the per-route request table ------------------------------------------

JUNK_HASH = "0" * 40


def _table(sim) -> list[dict]:
    """One request per registered route: method, path parameters, and a body
    that is valid and safe against the simulator. `gate` names the gate the
    request must be refused on when the device declines everything.

    Built against the plain simulator so slot-dependent values (a stored
    name, a saved design id) are real rather than guessed.
    """
    slot133 = slotops.describe(sim, 133)["name"]
    one_param = [STUB_PLAN["actions"][0]]
    design = designs.save({"name": "gate test", "summary": "", "author": "",
                           "actions": one_param, "preset": None,
                           "anchor": None, "offline": True, "profile": None,
                           "backend": None, "model": None})
    rows = [
        ("GET", "/", {}, None, None),
        ("GET", "/logo.png", {}, None, None),
        ("GET", "/api/link/stream", {}, None, None),
        ("POST", "/api/reconnect", {}, None, None),
        ("GET", "/api/state", {}, None, None),
        ("GET", "/api/describe/ready", {}, None, None),
        ("POST", "/api/describe/read", {}, {"source": "a bright clean tone"}, None),
        ("POST", "/api/describe/read/stream", {}, {"source": "a bright clean tone"}, None),
        ("POST", "/api/describe/build", {}, {"spec": {"summary": "bright clean"}}, None),
        ("POST", "/api/rig/correct", {}, {"graph": {"nodes": [{"id": "ts", "role": "drive"}], "edges": []},
                                          "text": "that pedal is a Klon"}, None),
        ("POST", "/api/describe/build/stream", {}, {"spec": {"summary": "bright clean"}}, None),
        ("POST", "/api/plan", {}, {"prompt": "a bit more drive"}, None),
        ("GET", "/api/tone-dir", {}, None, None),
        ("POST", "/api/tone-dir", {}, {"dir": ""}, None),
        ("POST", "/api/acquire", {}, {"query": "nothing on the catalogue"}, None),
        ("GET", "/api/gift-of-tone", {}, None, None),
        ("POST", "/api/gift-of-tone/fetch", {}, {"id": "no-such-entry"}, None),
        ("POST", "/api/artist-pack", {}, {"query": "sound like Nobody Here"}, None),
        ("POST", "/api/gift-of-tone/install", {}, {"id": "no-such-entry"}, None),
        # #149: a bad base64 body is refused before the parser; nothing reaches the unit.
        ("POST", "/api/captures/intake", {}, {"files": [{"name": "x.nam", "data": "!!"}]}, None),
        # #160: a link that is not an Axe-Change link is refused before any fetch.
        ("POST", "/api/axechange", {}, {"url": "not a link"}, None),
        # #101 #102 #103: a path outside the captures folder is refused before any read.
        ("POST", "/api/measure", {}, {"path": "/nowhere/x.wav"}, None),
        ("POST", "/api/measure/balance", {}, {"captures": [{"scene": 1, "role": "rhythm", "path": "/nowhere/x.wav"}]}, None),
        # #104: a path outside the captures folder is refused before any measurement or device read.
        ("POST", "/api/sound-check", {}, {"captures": [{"scene": 1, "role": "rhythm", "path": "/nowhere/x.wav"}]}, None),
        # #104: an invalid scene role is refused before the routing change or any capture.
        ("POST", "/api/sound-check/remeasure", {}, {"scenes": [{"scene": 1, "role": "verse"}]}, None),
        # #105: the references folder is listed, never written; a path outside the two folders is refused.
        ("GET", "/api/references", {}, None, None),
        ("POST", "/api/tone-match", {}, {"build": "/nowhere/x.wav", "reference": "/nowhere/y.wav"}, None),
        # #88: TONE3000 sign-in; login without a key is 409, the callback without a pending login 400,
        # status and logout touch the token file only; no route touches the device.
        ("GET", "/api/tone3000/login", {}, None, None),
        ("GET", "/api/tone3000/callback", {}, None, None),
        ("GET", "/api/tone3000/status", {}, None, None),
        ("POST", "/api/tone3000/logout", {}, None, None),
        ("GET", "/api/tone3000/load", {}, None, None),
        ("POST", "/api/install-cab", {}, {"hash": JUNK_HASH, "bank": 1, "number": 1},
         "installs_files"),
        ("POST", "/api/install", {}, {"hash": JUNK_HASH, "slot": 138}, "installs_files"),
        # After the two installs: parsing clears the pending file.
        ("POST", "/api/install/parse", {},
         {"data": base64.b64encode(b"not a preset file").decode()}, None),
        ("GET", "/api/store-slots", {}, None, None),
        ("POST", "/api/store-slots", {}, {"spec": "133-148", "preview": True}, None),
        ("GET", "/api/presets", {}, None, None),
        ("GET", "/api/presets/stream", {}, None, None),
        ("POST", "/api/preset", {}, {"number": 0}, None),
        # Before any route that loads another preset: a restore refuses when
        # the loaded preset is not the one the snapshot was captured on.
        ("GET", "/api/snapshots", {}, None, None),
        ("POST", "/api/snapshot", {}, {"slot": "b"}, None),
        ("POST", "/api/restore", {}, {"slot": "a"}, None),
        ("POST", "/api/copy-effects/nl", {},
         {"text": "copy just the settings of the delay from preset 1"}, None),
        ("POST", "/api/level-adjust", {}, {"text": "turn everything down 1 dB"}, None),
        ("POST", "/api/copy-effects", {},
         {"source": "1", "effects": ["DELAY"], "scene_aware": False}, None),
        ("POST", "/api/reorder", {},
         {"move": "delay", "ref": "cab", "position": "before"}, "topology>=SELECTED"),
        ("POST", "/api/compose", {},
         {"target": 135, "base": "0", "take": [], "name": "Composed", "store": False},
         "can_rename"),
        ("GET", "/api/models", {}, None, None),
        ("GET", "/api/grid", {}, None, None),
        ("GET", "/api/slot/{slot}", {"slot": 0}, None, None),
        ("POST", "/api/rename-slot", {}, {"slot": 134, "name": "Renamed"}, "can_rename"),
        ("POST", "/api/clear-slot", {}, {"slot": 133, "confirm_name": slot133},
         "topology>=SELECTED"),
        ("POST", "/api/build-scratch", {}, {"slot": 136}, "topology>=SELECTED"),
        ("POST", "/api/new-preset", {}, {"slot": 137}, "topology>=SELECTED"),
        ("POST", "/api/_moddebug", {}, {"slot": 1}, None),
        ("POST", "/api/health", {}, None, None),
        ("POST", "/api/health/stream", {}, None, None),
        ("GET", "/api/shared", {}, None, None),
        ("POST", "/api/shared/sweep", {}, None, None),
        ("POST", "/api/gig", {}, {"on": False}, None),
        ("GET", "/api/recipes", {}, None, None),
        ("POST", "/api/recipes/plan", {},
         {"recipe": {"name": "r", "title": "r", "actions": one_param}}, None),
        ("GET", "/api/share/status", {}, None, None),
        ("POST", "/api/share/sync", {}, None, None),
        ("POST", "/api/share/used", {}, {"name": "r"}, None),
        ("POST", "/api/recipes/save", {},
         {"recipe": {"name": "saved", "title": "saved", "actions": one_param}}, None),
        ("GET", "/api/profile", {}, None, None),
        ("POST", "/api/profile/export", {}, None, None),
        ("POST", "/api/profile/load", {}, {"profile": None}, None),
        ("GET", "/api/designs", {}, None, None),
        ("POST", "/api/designs", {}, {"name": "d", "actions": one_param}, None),
        ("DELETE", "/api/designs/{design_id}", {"design_id": design["id"]}, None, None),
        ("GET", "/api/designs/{design_id}/recipe", {"design_id": design["id"]}, None, None),
        ("POST", "/api/designs/{design_id}/check", {"design_id": design["id"]}, None, None),
        ("GET", "/api/gig", {}, None, None),
        ("GET", "/api/version", {}, None, None),
        ("POST", "/api/version/check", {}, None, None),
        ("GET", "/api/diagnostics/share-package", {}, None, None),
        ("POST", "/api/update", {}, None, None),
        ("GET", "/api/ir/status", {}, None, None),
        ("GET", "/api/ir/recommend", {}, None, None),
        ("GET", "/api/ir/blend", {}, None, None),
        ("GET", "/api/user-cabs", {}, None, None),
        ("POST", "/api/user-cabs", {}, {"ordinal": 0, "name": "my ir"}, None),
        ("GET", "/api/ir/search", {}, None, None),
        ("POST", "/api/user-cabs/link", {}, {"ordinal": 0, "path": ""}, None),
        ("GET", "/api/ir/audition", {}, None, None),
        # #82/#83: the on-rig audition is two ungated CABINET parameter
        # writes in the edit buffer, and the shortlist reads the catalog.
        ("GET", "/api/cab/shortlist", {}, None, None),
        ("GET", "/api/cab/audition", {}, None, None),
        ("POST", "/api/cab/audition", {}, {"bank": 3, "ordinal": 40}, None),
        ("POST", "/api/cab/audition/end", {}, None, None),
        # #94: the target-device seam. Selecting reads the environment and
        # swaps the context; neither touches a gated method.
        # Epic A: advice-only routes; scene sources select scenes (ungated).
        ("POST", "/api/advise/compare", {}, {"a": "scene 1", "b": "scene 2"}, None),
        ("POST", "/api/advise/gap", {}, {"a": "scene 1", "b": "scene 2"}, None),
        ("POST", "/api/advise/diagnose", {}, {"symptom": "muddy"}, None),
        ("GET", "/api/device", {}, None, None),
        ("POST", "/api/device/select", {}, {"kind": "fm9"}, None),
        ("GET", "/api/ir/audition/integrity", {}, None, None),
        ("POST", "/api/ir/config", {}, {"url": ""}, None),
        ("GET", "/api/ai-settings", {}, None, None),
        ("GET", "/api/fm3/port", {}, None, None),
        ("POST", "/api/fm3/port", {}, {"port": ""}, None),
        ("GET", "/api/ai-settings/models", {}, None, None),
        ("GET", "/api/ai-settings/setup", {}, None, None),
        ("POST", "/api/chat", {}, {"messages": [{"role": "user", "content": "hi"}]}, None),
        ("POST", "/api/plan/stream", {}, {"prompt": "a bit more drive"}, None),
        ("POST", "/api/chat/stream", {}, {"messages": [{"role": "user", "content": "hi"}]}, None),
        ("POST", "/api/ai-settings/setup/run", {}, {"step": "not a step"}, None),
        ("POST", "/api/ai-settings", {}, {"backend": "cli"}, None),
        ("POST", "/api/apply", {},
         {"actions": [{"kind": "rename_preset", "block": "PRESET", "instance": 1,
                       "type_name": "Gate Test"}]}, "can_rename"),
        ("POST", "/api/apply/stream", {},
         {"actions": [{"kind": "rename_preset", "block": "PRESET", "instance": 1,
                       "type_name": "Gate Test"}]}, "can_rename"),
        ("POST", "/api/plan/revise", {}, {"actions": one_param}, None),
    ]
    return [{"method": m, "path": p, "params": pp, "json": body, "gate": gate}
            for m, p, pp, body, gate in rows]


#: The same routes again with bodies that reach the OTHER gates a plan can
#: need, so each reachable gate is refused by name at least once. Every one
#: is a single action, which is a direct gesture and needs no plan digest.
EXTRA_PROBES = [
    ("POST", "/api/apply", {"actions": [{"kind": "add_block", "block": "wah",
                                          "instance": 1}]}, "topology>=SELECTED"),
    ("POST", "/api/apply", {"actions": [{"kind": "reorder", "block": "delay",
                                          "ref": "cab", "position": "before"}]},
     "topology>=SELECTED"),
    ("POST", "/api/apply", {"actions": [{"kind": "bind_pedal", "block": "delay",
                                          "instance": 1, "param": "DELAY_MIX"}]},
     "has_modifiers"),
    ("POST", "/api/apply", {"actions": [{"kind": "unbind_pedal", "block": "delay",
                                          "instance": 1, "param": "DELAY_MIX"}]},
     "has_modifiers"),
    ("POST", "/api/apply", {"actions": [{"kind": "rename_scene", "block": "SCENE",
                                          "instance": 1, "value": 1,
                                          "type_name": "Clean"}]}, "can_rename"),
    ("POST", "/api/apply/stream", {"actions": [{"kind": "add_block", "block": "wah",
                                                 "instance": 1}]},
     "topology>=SELECTED"),
]


def _registered_routes() -> set[tuple[str, str]]:
    out = set()
    for r in server.app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods:
                out.add((m, r.path))
    return out


def _drive(client: TestClient, row: dict) -> dict:
    """One request. A stream is consumed to its first non-ping event and,
    when the stream is finite, to its end, so no worker outlives the request
    and the next route does not queue behind it. The link stream never ends
    and is left after its first event."""
    path = row["path"].format(**row["params"])
    kw = {}
    if row["json"] is not None:
        kw["json"] = row["json"]
    stream = row["path"].endswith("/stream")
    if not stream:
        r = client.request(row["method"], path, **kw)
        body = None
        if r.headers.get("content-type", "").startswith("application/json"):
            body = r.json()
        return {"status": r.status_code, "json": body, "first_event": None}
    with client.stream(row["method"], path, **kw) as r:
        if not r.headers.get("content-type", "").startswith("text/event-stream"):
            raw = b"".join(r.iter_bytes())
            return {"status": r.status_code, "json": json.loads(raw),
                    "first_event": None}
        first = None
        for line in r.iter_lines():
            if line.startswith("event: ") and line != "event: ping":
                first = line[len("event: "):].strip()
                if row["path"] == "/api/link/stream":
                    break
        return {"status": r.status_code, "json": None, "first_event": first}


def _run_table(client: TestClient, rows: list[dict]) -> list[dict]:
    return [_drive(client, row) for row in rows]


REFUSAL_KEYS = {"refused", "capability", "method", "route"}


# --- the substitution proof -----------------------------------------------

def test_request_table_covers_every_registered_route(world):
    registered = _registered_routes()
    assert len(registered) >= 82, len(registered)
    listed = {(row["method"], row["path"]) for row in _table(SimFM9(server.reg))}
    assert listed == registered, {
        "unlisted routes": sorted(registered - listed),
        "stale table rows": sorted(listed - registered)}
    for m, p, _b, _g in EXTRA_PROBES:
        assert (m, p) in registered


def test_sentinel_substitution_no_gated_method_fires_and_every_decline_is_a_409(world):
    """The proof the issue asked for. Baseline first: the same table against
    the plain simulator. Then the sentinel: every gate declined, every gated
    method a tripwire, every route driven."""
    baseline_dev = SimFM9(server.reg)
    rows = _table(baseline_dev)
    _install(baseline_dev)
    baseline = _run_table(TestClient(server.app), rows)

    sentinel = SentinelDevice(SimFM9(server.reg))
    _install(sentinel)
    client = TestClient(server.app)
    got = _run_table(client, rows)
    probes = [_drive(client, {"method": m, "path": p, "params": {}, "json": b,
                              "gate": g}) for m, p, b, g in EXTRA_PROBES]

    assert sentinel.fired == [], (
        f"gated methods reached the device past the gate: {sentinel.fired}")

    refused_on = set()
    problems = []
    for row, base, out in zip(rows, baseline, got):
        where = f"{row['method']} {row['path']}"
        if row["gate"]:
            if out["status"] != 409:
                problems.append(f"{where}: expected 409, got {out['status']} "
                                f"{out['json']}")
                continue
            body = out["json"]
            if (set(body) != REFUSAL_KEYS or body["refused"] is not True
                    or body["capability"] != row["gate"]
                    or body["route"] != row["path"].format(**row["params"])
                    or body["method"] not in GATE_MATRIX[row["gate"]]):
                problems.append(f"{where}: refusal shape wrong: {body}")
            refused_on.add(body["capability"])
        else:
            if out["status"] == 500 or base["status"] == 500:
                problems.append(f"{where}: 500 (baseline {base['status']}, "
                                f"sentinel {out['status']})")
            if out["status"] != base["status"]:
                problems.append(f"{where}: baseline {base['status']}, sentinel "
                                f"{out['status']} {out['json']}")
            if out["first_event"] != base["first_event"]:
                problems.append(f"{where}: first event changed: baseline "
                                f"{base['first_event']!r}, sentinel "
                                f"{out['first_event']!r}")
            if isinstance(base["json"], dict) and isinstance(out["json"], dict) \
                    and set(base["json"]) != set(out["json"]):
                problems.append(f"{where}: response keys changed")
            if out["status"] == 409 and isinstance(out["json"], dict) \
                    and out["json"].get("refused") is True:
                problems.append(f"{where}: refused on a gate the table did "
                                f"not expect: {out['json']}")
    for (m, p, body, gate), out in zip(EXTRA_PROBES, probes):
        if out["status"] != 409 or (out["json"] or {}).get("capability") != gate:
            problems.append(f"probe {m} {p} {body}: expected 409 on {gate}, "
                            f"got {out['status']} {out['json']}")
        else:
            refused_on.add(gate)
    assert not problems, "\n".join(problems)
    assert refused_on == REACHABLE_GATES, refused_on
    assert world == [], f"network reached: {world}"


def test_the_refusal_names_the_precise_gate_not_only_the_first_one_declined(world):
    """A device that CAN place blocks but cannot draw cables (a SELECTED
    topology, the HeadRush shape) is refused on the wiring gate by name."""
    selected = dataclasses.replace(DECLINE_ALL, topology=Topology.SELECTED)
    sentinel = SentinelDevice(SimFM9(server.reg), capabilities=selected)
    _install(sentinel)
    r = TestClient(server.app).post("/api/build-scratch", json={"slot": 136})
    assert r.status_code == 409
    assert r.json() == {"refused": True, "capability": "topology==CONSTRUCTED",
                        "method": "connect_cells", "route": "/api/build-scratch"}
    assert sentinel.fired == []


def test_the_debug_pair_is_off_without_the_variable(world, monkeypatch):
    """The TONECOMMAND_DEBUG _send/_drain pair is FM9-only and allowlisted;
    with the variable unset the route answers 404 before the handle is
    touched, on the sentinel as on the simulator."""
    monkeypatch.delenv("TONECOMMAND_DEBUG", raising=False)
    sentinel = SentinelDevice(SimFM9(server.reg))
    _install(sentinel)
    r = TestClient(server.app).post("/api/_moddebug",
                                    json={"slot": 1, "op": "poke", "pid": 0,
                                          "value": 0.5})
    assert r.status_code == 404
    assert sentinel.fired == []


# --- the broad-except audit ----------------------------------------------

def _except_exception_blocks(tree):
    """Every `except Exception` handler in server.py by AST identity: the
    enclosing function's qualified name and the ordinal of the handler within
    that function in source order. Returns {(qualname, ordinal): (handler,
    preceding handlers, try body)}."""
    found: dict[str, list] = {}

    def visit(node, qual):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, f"{qual}.{child.name}" if qual else child.name)
                continue
            if isinstance(child, ast.Try):
                for i, h in enumerate(child.handlers):
                    if isinstance(h.type, ast.Name) and h.type.id == "Exception":
                        found.setdefault(qual, []).append(
                            (h.lineno, h, child.handlers[:i], child.body))
            visit(child, qual)

    visit(tree, "")
    out = {}
    for qual, items in found.items():
        for n, (_line, h, before, body) in enumerate(
                sorted(items, key=lambda x: x[0]), 1):
            out[(qual, n)] = (h, before, body)
    return out


def _handles_decline_first(before) -> bool:
    return any(isinstance(h.type, ast.Name) and h.type.id == "CapabilityDeclined"
               for h in before)


def test_broad_except_audit_every_block_reraises_the_decline_or_says_why_it_cannot_see_one():
    """86 `except Exception` blocks, each accounted for by identity. A block
    that a decline can reach re-raises CapabilityDeclined before its handler
    runs; the rest state why a decline cannot reach them. An unlisted block,
    or a listed identity that no longer exists, fails."""
    blocks = _except_exception_blocks(ast.parse(SERVER.read_text(encoding="utf-8")))
    listed = {(b["function"], b["ordinal"]): b["disposition"]
              for b in json.loads(AUDIT.read_text(encoding="utf-8"))["blocks"]}
    assert set(blocks) == set(listed), {
        "unlisted": sorted(set(blocks) - set(listed)),
        "stale": sorted(set(listed) - set(blocks))}

    gated = set(GATED_METHODS)
    reaching = {"require_capability", "require_for_actions", "run_action",
                "_take", "_bind_pedal", "_unbind_pedal", "_add_block"}
    problems = []
    for key, (handler, before, body) in blocks.items():
        disposition = listed[key]
        if _handles_decline_first(before):
            if not disposition.startswith(("re-raises", "converted")):
                problems.append(f"{key}: handles CapabilityDeclined first but "
                                f"its disposition says {disposition!r}")
            continue
        if not disposition.startswith("unreachable:") or len(disposition) < 30:
            problems.append(f"{key} (line {handler.lineno}): no re-raise and no "
                            f"reason a decline cannot reach it: {disposition!r}")
            continue
        # A claim of unreachability must not sit over a body that names a
        # gated method or a helper that reaches one.
        mod = ast.Module(body=body, type_ignores=[])
        attrs = {n.attr for n in ast.walk(mod) if isinstance(n, ast.Attribute)}
        calls = {n.func.id for n in ast.walk(mod)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        if (attrs & gated) or (calls & reaching):
            problems.append(f"{key} (line {handler.lineno}): says unreachable "
                            f"but its try body reaches "
                            f"{sorted((attrs & gated) | (calls & reaching))}")
    assert not problems, "\n".join(problems)

    # The debug-only pair is a listed, re-raising block, not an exemption.
    assert listed[("api_moddebug", 1)].startswith("re-raises")
    # The block the issue named.
    assert listed[("_will_lay_template", 1)].startswith("re-raises")


def test_audit_counts_are_reported_honestly():
    """The numbers the changelog states, measured rather than remembered."""
    blocks = _except_exception_blocks(ast.parse(SERVER.read_text(encoding="utf-8")))
    reraised = sum(1 for _h, before, _b in blocks.values()
                   if _handles_decline_first(before))
    assert len(blocks) == 90
    assert reraised == 36
    assert len(blocks) - reraised == 54


def test_capability_declined_is_its_own_type_and_the_handler_shapes_the_409(world):
    exc = server.CapabilityDeclined("can_rename", "rename_preset")
    assert not isinstance(exc, (AttributeError, LookupError))
    assert exc.capability == "can_rename" and exc.method == "rename_preset"
    assert exc.payload("/x") == {"refused": True, "capability": "can_rename",
                                 "method": "rename_preset", "route": "/x"}


def test_will_lay_template_audit_keeps_its_three_outcomes_distinct(world, monkeypatch):
    """The clearest case in the audit: `except Exception: return False` here
    would have absorbed a decline and silently switched the build to the
    splice path."""
    class Reads:
        def __init__(self, grid):
            self._grid = grid

        def read_grid(self):
            if isinstance(self._grid, BaseException):
                raise self._grid
            return self._grid

    body = server.PromptBody(prompt="x")
    monkeypatch.setattr(server, "get_fm9", lambda: Reads([]))
    assert server._will_lay_template(body) is True
    monkeypatch.setattr(server, "get_fm9",
                        lambda: Reads(RuntimeError("device busy")))
    assert server._will_lay_template(body) is False
    monkeypatch.setattr(server, "get_fm9", lambda: Reads(
        server.CapabilityDeclined("topology>=SELECTED", "place_block")))
    with pytest.raises(server.CapabilityDeclined):
        server._will_lay_template(body)


# --- the invariants survive gate insertion ---------------------------------

WRITE_METHODS = {
    "select_preset", "set_scene", "set_bypass", "set_channel",
    "set_param_display", "set_param_ordinal", "set_params_batch",
    "store_preset", "set_tempo", "place_block", "reorder_block",
    "connect_cells", "splice_block", "bind_modifier", "clear_modifier",
    "install_preset", "install_user_cab_at", "rename_preset", "rename_scene",
    "select_topology", "set_scene_slot", "send_preset_file", "_send",
}

INSTALL_FNS = frozenset({0x77, 0x78, 0x79, 0x7A, 0x7B, 0x7C})


def _is_wire_write(msg) -> bool:
    """Whether a message the simulator's port received changes device state.
    Program and bank changes select a preset; SysEx is classified by the
    simulator's own table, plus the preset and cab install families."""
    if msg.type != "sysex":
        return True
    d = list(msg.data)
    if len(d) <= 5:
        return False
    if d[4] in INSTALL_FNS:
        return True
    return fm9sim._classify(d) == "write"


class _Recorder:
    """A recording sentinel over a simulator, with the wire observed too."""

    def __init__(self, capabilities=None):
        self.sim = SimFM9(server.reg)
        self.calls: list = []
        self.wire: list = []
        self.device = SentinelDevice(
            self.sim, capabilities=capabilities or self.sim.capabilities(),
            record=self.calls)
        real_send = self.sim.outp.send

        def spy(msg):
            self.wire.append(msg)
            return real_send(msg)
        self.sim.outp.send = spy

    def writes(self) -> list:
        return [c for c in self.calls if c[0] in WRITE_METHODS]

    def wire_writes(self) -> list:
        return [m for m in self.wire if _is_wire_write(m)]

    def clear(self):
        self.calls.clear()
        self.wire.clear()


def _write_rows(rows):
    return [row for row in rows if row["gate"]]


_FULL_RUN: dict = {}


def _full_accepting_run() -> _Recorder:
    """The whole table and every probe, once, on the accepting recorder.
    Two invariants read the same run, and a run is a few minutes of
    simulator settle windows, so it is shared rather than repeated."""
    if "rec" not in _FULL_RUN:
        import tempfile
        mp = pytest.MonkeyPatch()
        try:
            _stub_world(mp, pathlib.Path(tempfile.mkdtemp(prefix="gates-")))
            rec = _Recorder()
            rows = _table(rec.sim)
            _install(rec.device)
            client = TestClient(server.app)
            _run_table(client, rows)
            for m, p, b, _g in EXTRA_PROBES:
                _drive(client, {"method": m, "path": p, "params": {},
                                "json": b, "gate": None})
        finally:
            mp.undo()
            server._fm9 = None
        _FULL_RUN["rec"] = rec
    return _FULL_RUN["rec"]


def test_invariant_capability_check_runs_before_any_write_on_every_write_route(world):
    """A decline arrives with zero device writes: method level and wire level
    both empty. Every write route in the table and every extra probe."""
    rec = _Recorder(capabilities=DECLINE_ALL)
    rows = _write_rows(_table(rec.sim))
    _install(rec.device)
    client = TestClient(server.app)
    probes = [{"method": m, "path": p, "params": {}, "json": b, "gate": g}
              for m, p, b, g in EXTRA_PROBES]
    for row in rows + probes:
        rec.clear()
        out = _drive(client, row)
        where = f"{row['method']} {row['path']} {row['json']}"
        assert out["status"] == 409, f"{where}: {out}"
        assert rec.writes() == [], f"{where}: wrote before the decline"
        assert rec.wire_writes() == [], f"{where}: transmitted before the decline"
        assert rec.device.fired == []


def test_invariant_1_a_plan_without_its_reviewed_revision_transmits_nothing(world):
    """The confirmation server.py already requires: a multi-action plan must
    name the revision it was reviewed as (check_revision). Driven without it,
    and with a digest that matches nothing, both twins send nothing, on the
    gated server exactly as before."""
    rec = _Recorder()
    _install(rec.device)
    client = TestClient(server.app)
    plan = [{"kind": "set_param", "block": "amp", "instance": 1,
             "param": "DISTORT_DRIVE", "value": 5.0},
            {"kind": "set_bypass", "block": "delay", "instance": 1,
             "bypassed": True}]
    for body in ({"actions": plan},
                 {"actions": plan, "plan_digest": "0000000000000000"}):
        for path in ("/api/apply", "/api/apply/stream"):
            rec.clear()
            out = _drive(client, {"method": "POST", "path": path, "params": {},
                                  "json": body, "gate": None})
            assert out["status"] == 200, out
            assert rec.writes() == [], f"{path} {body}: {rec.writes()}"
            assert rec.wire_writes() == [], f"{path} {body}: transmitted"
    # And the positive control: the same plan, reviewed, does transmit.
    digest = server.register_revision([server.Action(**a) for a in plan], "test")
    rec.clear()
    r = client.post("/api/apply", json={"actions": plan, "plan_digest": digest})
    assert r.status_code == 200 and r.json().get("refused") is None
    assert rec.wire_writes(), "the reviewed plan should have transmitted"


def test_invariant_2_firmware_and_bootloader_are_unreachable_by_construction():
    """No builder for them exists, the handle has no such method, the guard
    refuses an undeclared function id, and nothing a full run transmits lies
    outside the three declared allowlists."""
    builders = [n for n in dir(fp) if n.startswith("build_")]
    forbidden = [n for n in builders
                 if any(w in n for w in ("bootloader", "flash", "update",
                                         "upgrade", "erase"))
                 or ("firmware" in n and n != "build_get_firmware")]
    assert forbidden == [], forbidden
    for name in ("update_firmware", "send_firmware", "bootloader",
                 "enter_bootloader", "flash", "erase"):
        assert not hasattr(FM9, name)
    with pytest.raises(BrickGuardRefusal):
        FM9.guard.check(0x7D)
    with pytest.raises(BrickGuardRefusal):
        FM9.guard.check(0x7F)
    allowed = FM9.SENDABLE_FNS | FM9.install_guard.kinds | FM9.cab_guard.kinds

    rec = _full_accepting_run()
    fns = {list(m.data)[4] for m in rec.wire
           if m.type == "sysex" and len(m.data) > 5}
    assert fns, "the run transmitted nothing at all, so this proves nothing"
    assert fns <= allowed, sorted(hex(f) for f in fns - allowed)
    assert not any(w in n for n in dir(rec.device) for w in ("bootloader", "firmware_update"))


def test_invariant_5_an_undo_snapshot_is_taken_before_any_accepted_write(world, monkeypatch):
    """On the accepting recorder, the snapshot capture precedes the first
    write on both write paths that take one: a direct apply and a reorder."""
    rec = _Recorder()
    _install(rec.device)
    client = TestClient(server.app)
    real_take = server._take

    def take(slot):
        rec.calls.append(("_take", (slot,), {}))
        return real_take(slot)
    monkeypatch.setattr(server, "_take", take)

    for path, body in (("/api/apply", {"actions": [
                            {"kind": "set_param", "block": "amp", "instance": 1,
                             "param": "DISTORT_DRIVE", "value": 4.0}]}),
                       ("/api/reorder", {"move": "delay", "ref": "cab",
                                         "position": "before"})):
        rec.clear()
        server._snaps["undo"] = None
        r = client.post(path, json=body)
        assert r.status_code in (200, 422), (path, r.status_code, r.json())
        names = [c[0] for c in rec.calls]
        assert "_take" in names, f"{path}: no undo snapshot was taken"
        first_write = next(i for i, n in enumerate(names) if n in WRITE_METHODS)
        assert names.index("_take") < first_write, (
            f"{path}: the first write came before the undo snapshot")
        assert rec.calls[names.index("_take")][1] == ("undo",)
        assert server._snaps["undo"] is not None


def test_invariant_6_pedal_1_is_never_touched_by_any_route():
    """Across the whole table and the probes on the accepting recorder: no
    binding is made to Pedal 1's source, no slot driven by Pedal 1 is cleared,
    and the simulator's modifier table ends the run with no Pedal 1 slot."""
    rec = _full_accepting_run()
    binds = [c for c in rec.calls if c[0] == "bind_modifier"]
    assert binds, "no binding was made, so the run proves nothing about pedals"
    for _name, args, kwargs in binds:
        source = args[3] if len(args) > 3 else kwargs.get("source_ordinal")
        assert source != server.PEDAL_1_SOURCE, f"bound to Pedal 1: {args}"
    for _name, args, _kw in [c for c in rec.calls if c[0] == "clear_modifier"]:
        slot = args[0]
        fields = rec.sim.sim_core.st.buffer["modifiers"].get(slot) or []
        assert not (len(fields) > fp.MOD_PID_SOURCE
                    and fields[fp.MOD_PID_SOURCE] == server.PEDAL_1_SOURCE)
    for slot, fields in rec.sim.sim_core.st.buffer["modifiers"].items():
        assert fields[fp.MOD_PID_SOURCE] != server.PEDAL_1_SOURCE, (
            f"modifier slot {slot} ended the run on Pedal 1")


def test_changelog_names_the_gates_and_touched_files_have_no_em_dash():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    # The section this work shipped in (it sat under Unreleased until 1.3.0).
    section = changelog.split("## 1.3.0", 1)[1].split("\n## 1.2", 1)[0]
    assert "CapabilityDeclined" in section and "#111" in section
    em_dash = chr(0x2014)
    for rel in ("server.py", "tests/test_capability_gates.py",
                "tests/sentinel_device.py", "tests/data/broad_except_audit.json",
                "CHANGELOG.md", "ARCHITECTURE.md"):
        assert em_dash not in (ROOT / rel).read_text(encoding="utf-8"), f"em dash in {rel}"
