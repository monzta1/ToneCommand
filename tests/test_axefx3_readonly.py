"""A small independent fake III, literal read forms, no physical MIDI ports."""
from types import SimpleNamespace

import mido
import pytest
from fastapi.testclient import TestClient

import server
from devices.axefx3 import readonly_protocol as p
from devices.axefx3.readonly_adapter import (AxeFxIII, ReadOnlyOutput, ReadOnlyRegistry,
                                   READ_ONLY, snapshot)
from fm9 import protocol as shared
from fm9.adapter import DeviceAdapter, conformance
from fm9.device import FM9, FM9NotFound, ReadOnly
from fm9.safety import BrickGuardRefusal


def name_field(text):
    return list(text.encode("ascii").ljust(32, b"\0"))


class FakePorts:
    """Answers read requests only. This is not the FM9 simulator."""

    def __init__(self):
        self.sent, self.queue, self.closes = [], [], []
        self.preset, self.scene = 320, 0
        self.reply = self.answer
        self.inp = SimpleNamespace(iter_pending=self.pending,
                                   close=lambda: self.closes.append("in"))
        self.outp = SimpleNamespace(send=self.send,
                                    close=lambda: self.closes.append("out"))

    def pending(self):
        while self.queue:
            yield self.queue.pop(0)

    def send(self, message):
        frame = [0xF0, *message.data, 0xF7]
        assert p.allowed(frame), "the fake received something other than a read"
        self.sent.append(frame)
        for data in self.reply(frame):
            self.queue.append(mido.Message("sysex", data=data))

    def answer(self, frame):
        function, payload = frame[5], frame[6:-2]
        if function == 8:
            body = [33, 0]
        elif function == 0x0D:
            number = self.preset if payload == [127, 127] else shared.decode14(*payload)
            body = [*shared.encode14(number), *name_field("Read Test")]
        elif function == 0x0C:
            body = [self.scene]
        elif function == 0x0E:
            scene = self.scene if payload == [127] else payload[0]
            body = [scene, *name_field("Scene " + str(scene + 1))]
        elif function == 0x13:
            body = [58, 0, 64, 62, 0, 67, 78, 0, 64, 78, 1, 64]
        else:
            body = payload[:2] + [0]
        return [p.envelope(function, body)[1:-1]]


@pytest.fixture
def device():
    ports = FakePorts()
    dev = AxeFxIII((ports.inp, ports.outp))
    yield dev, ports
    dev.close()


@pytest.mark.parametrize("function,payload", [
    (8, []), (0x13, []), (0x0D, [0, 0]), (0x0D, [127, 3]),
    (0x0D, [127, 127]), (0x0E, [0]), (0x0E, [7]), (0x0E, [127]),
    (0x0C, [127]), (0x0A, [58, 0, 127]), (0x0B, [78, 1, 127]),
])
def test_exact_allowed_reads(function, payload):
    assert p.allowed(p.envelope(function, payload))


def test_known_full_firmware_responses_get_labels_without_write_authority():
    from devices.axefx3 import firmware_identity,fw33_profile
    from tests.test_axefx3_firmware_identity import BETA5
    unknown=list(BETA5);unknown[12]^=1;unknown[-1]=shared.checksum(unknown[:-1])
    for reply,label in ((fw33_profile.IDENTITY,fw33_profile.KEY),(BETA5,firmware_identity.BETA5_KEY),
                        (unknown,'97.00'),(p.envelope(8,[97,0])[1:-1],'97.00')):
        ports=FakePorts();answer=ports.answer
        ports.reply=lambda frame,r=reply: [r] if frame[5]==8 else answer(frame)
        dev=AxeFxIII((ports.inp,ports.outp))
        try:
            assert dev.firmware_label()==label
            assert all(p.allowed(frame) for frame in ports.sent)
            assert ReadOnlyRegistry().params=={}
            assert not dev.capabilities().can_rename and not dev.capabilities().can_verify
            with pytest.raises((ReadOnly,BrickGuardRefusal)):
                dev._send(p.envelope(1,[9,0]+[0]*13))
        finally:dev.close()


def test_readonly_firmware_label_ignores_a_delayed_cursor_reply():
    from tests.test_axefx3_firmware_identity import BETA5
    from devices.axefx3 import firmware_identity
    ports=FakePorts();answer=ports.answer
    ports.reply=lambda frame: [p.envelope(1,[48,0]+[0]*13)[1:-1],BETA5] if frame[5]==8 else answer(frame)
    dev=AxeFxIII((ports.inp,ports.outp))
    try:
        before=len(ports.sent)
        assert dev.firmware_label()==firmware_identity.BETA5_KEY
        assert ports.sent[before:]==[p.envelope(8,[])]
    finally:dev.close()


@pytest.mark.parametrize("function,payload", [
    (1, [0x10, 0, 58, 0, 1, 0]), (1, [9, 0] + [0] * 13),
    (0x1F, [58, 0]), (0x0A, [58, 0, 0]), (0x0A, [58, 0, 1]),
    (0x0B, [58, 0, 2]), (0x0C, [0]), (0x0D, [0, 4]),
    (0x0D, [0, 0, 0]), (0x0E, [8]), (8, [0]), (0x13, [0]),
    (0x64, []), (0x77, [0]), (0x7D, []),
])
def test_non_reads_fail_at_final_output(function, payload):
    raw = SimpleNamespace(send=lambda message: pytest.fail("a non-read reached MIDI"))
    frame = p.envelope(function, payload)
    assert not p.allowed(frame)
    with pytest.raises((ReadOnly, BrickGuardRefusal)):
        ReadOnlyOutput(raw).send(mido.Message("sysex", data=frame[1:-1]))


@pytest.mark.parametrize("message", [
    mido.Message("program_change", program=3),
    mido.Message("control_change", control=0, value=1),
    mido.Message("control_change", control=6, value=127),
    mido.Message("note_on", note=60), mido.Message("clock"),
])
def test_channel_and_realtime_messages_refused(device, message):
    dev, ports = device
    before = list(ports.sent)
    with pytest.raises(ReadOnly):
        dev.outp.send(message)
    assert ports.sent == before


def test_protocol_rejects_wrong_product_checksum_and_nonseptets():
    good = p.envelope(8, [])
    assert not p.allowed(shared.envelope(8, [], model=0x12))
    assert not p.allowed(good[:-2] + [good[-2] ^ 1, 0xF7])
    assert not p.allowed([0xF0, 0, 1, 116, 16, 8, 128, 0, 0xF7])
    assert not p.allowed([])
    assert not p.valid_reply([0, 1, 116, 16, 8, True])


def test_contract_and_non_writing_capabilities(device):
    dev, _ = device
    assert conformance(dev) == []
    assert isinstance(dev, DeviceAdapter) and not isinstance(dev, FM9)
    caps = dev.capabilities()
    assert caps.reads_slot_names and caps.has_scenes
    assert not caps.can_verify and not caps.stores_presets
    assert not caps.has_modifiers and not caps.can_rename and not caps.plays_captures
    assert not caps.installs_files and not caps.topology
    reg = ReadOnlyRegistry()
    assert reg.model_byte == 16 and not reg.params and not reg.amp_roster and not reg.cab_rosters
    with pytest.raises(ReadOnly):
        reg.spec("DISTORT", 1)


@pytest.mark.parametrize("method,args", [
    ("select_preset", [321]), ("set_scene", [2]), ("set_bypass", [58, True]),
    ("set_channel", [58, 1]), ("set_param_display", [None, 5]),
    ("set_param_ordinal", [None, 2]), ("set_params_batch", [[]]),
    ("store_preset", [321]), ("get_param_display", [None]),
])
def test_all_core_mutations_decline_without_sending(device, method, args):
    dev, ports = device
    before = list(ports.sent)
    with pytest.raises(ReadOnly, match="read-only"):
        getattr(dev, method)(*args)
    assert dev.bulk_read(58) is None
    assert ports.sent == before


def test_reads_and_coherent_snapshot_keep_unknown_effect_ids(device):
    dev, ports = device
    got = snapshot(dev)
    assert got["connected"] and got["read_only"] and got["navigation_read_only"]
    assert got["preset"] == dict(number=320, editor=320, name="Read Test")
    assert got["scene"] == dict(number=1, name="Scene 1")
    assert got["firmware"] == "33.00" and len(got["scenes"]) == 8
    assert got["blocks"][1]["bypassed"] and got["blocks"][1]["channel"] == "B"
    assert got["blocks"][-1]["effect_id"] == 206
    assert got["blocks"][-1]["label"] == "Block 206"
    assert not got["values"] and not got["params"] and not got["mods"]
    assert all(p.allowed(frame) for frame in ports.sent)
    assert dev.slot_name(320).number == 320
    assert [s.number for s in dev.scan_slots(320, 321)] == [320, 321]


@pytest.mark.parametrize("change", ["preset", "scene"])
def test_transition_during_snapshot_refuses_mixed_state(device, monkeypatch, change):
    dev, ports = device
    original = dev.status_dump
    def transition():
        got = original()
        setattr(ports, change, getattr(ports, change) + 1)
        return got
    monkeypatch.setattr(dev, "status_dump", transition)
    with pytest.raises(FM9NotFound, match="changed"):
        snapshot(dev)


def test_reply_filters_wrong_product_bad_checksum_and_wrong_request(device):
    dev, ports = device
    def responses(frame):
        correct = ports.answer(frame)[0]
        wrong = shared.envelope(0x0D, [0, 0, *name_field("Wrong")], model=18)[1:-1]
        bad = correct[:-1] + [correct[-1] ^ 1]
        stale = p.envelope(0x0D, [1, 0, *name_field("Stale")])[1:-1]
        return [wrong, bad, stale, correct]
    ports.reply = responses
    assert dev.slot_name(320).number == 320
    ports.reply = lambda frame: []
    assert dev._request(8, [], lambda d: d, timeout=.01) is None


def test_constructor_failure_closes_both_ports_and_close_is_idempotent(monkeypatch):
    ports = FakePorts()
    monkeypatch.setattr(AxeFxIII, "firmware_label", lambda self: "")
    with pytest.raises(FM9NotFound):
        AxeFxIII((ports.inp, ports.outp))
    assert ports.closes == ["in", "out"]


def test_closed_device_never_sends_again(device):
    dev, ports = device
    dev.close()
    dev.close()
    assert ports.closes == ["in", "out"]
    with pytest.raises(FM9NotFound, match="closed"):
        dev.current_preset()


@pytest.mark.parametrize("scene", [0, 9, True, 2.5])
def test_invalid_scene_name_query_cannot_be_sent(device, scene):
    dev, ports = device
    before = list(ports.sent)
    with pytest.raises(ValueError):
        dev.scene_name(scene)
    assert ports.sent == before


def test_missing_scene_name_is_unknown_not_replaced_with_a_guess(device):
    dev, ports = device
    original = dev.scene_name
    dev.scene_name = lambda scene=None: None if scene == 3 else original(scene)
    got = snapshot(dev)
    assert got["scenes"][2] == dict(number=3, name=None)
    assert got["connected"]


def test_malformed_status_is_not_an_empty_grid(device):
    dev, ports = device
    bad = p.envelope(0x13, [58, 0])[1:-1]
    ports.reply = lambda frame: [bad]
    # Exercise the normal parser with a short timeout, not a replacement parser.
    request = dev._request
    dev._request = lambda fn, payload, parser: request(fn, payload, parser, timeout=.01)
    assert dev.status_dump() is None


@pytest.mark.parametrize("value", [-1, 512, True, 1.5])
def test_bad_name_slot_rejected_before_send(device, value):
    dev, ports = device
    before = list(ports.sent)
    with pytest.raises(ValueError):
        dev.slot_name(value)
    assert ports.sent == before


@pytest.fixture
def client(device, monkeypatch):
    dev, ports = device
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_selected_kind", {"kind": None})
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "detected_devices", lambda: [{"kind": "axefx3"}])
    monkeypatch.setattr("devices.axefx3.readonly_adapter.AxeFxIII", lambda **kwargs: dev)
    with TestClient(server.app) as http:
        assert http.post("/api/device/select", json={"kind": "axefx3"}).status_code == 200
        yield http, ports


def test_normal_devices_and_state_routes_read_without_writes(client):
    http, ports = client
    got = http.get("/api/state")
    assert got.status_code == 200, got.text
    assert got.json()["device"]["active"] == "axefx3"
    assert got.json()["read_only"] and got.json()["params"] == {}
    assert all(p.allowed(frame) for frame in ports.sent)


def test_plan_declines_before_ai_and_navigation_cannot_send(client, monkeypatch):
    http, ports = client
    monkeypatch.setattr(server.planner, "plan", lambda *a, **kw: pytest.fail("AI reached"))
    got = http.post("/api/plan", json={"prompt": "more gain"})
    assert got.status_code == 409 and got.json() == dict(error=READ_ONLY, read_only=True)
    before = list(ports.sent)
    got = http.post("/api/preset", json={"number": 321})
    assert got.status_code != 200 or not got.json().get("ok")
    assert all(p.allowed(frame) for frame in ports.sent)
    assert not any(f[5] == 0x0C and f[6] != 127 for f in ports.sent[len(before):])


def test_failed_device_selection_keeps_old_context(monkeypatch):
    monkeypatch.setattr(server, "_context", server._default_context)
    monkeypatch.setattr(server, "_plan_revisions", {})
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "detected_devices", lambda: [{"kind": "axefx3"}])
    def busy(**kwargs):
        raise OSError("port occupied")
    monkeypatch.setattr("devices.axefx3.readonly_adapter.AxeFxIII", busy)
    with TestClient(server.app) as http:
        got = http.post("/api/device/select", json={"kind": "axefx3"})
    assert got.status_code == 503
    assert server.device_context() is server._default_context
