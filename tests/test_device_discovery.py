"""Device discovery that tells the truth.

#259: the CoreMIDI bus watcher is live before the first request, however
the server is launched. #260: the ToneX Pedal is recognised, and offered for
connection only when a live ToneX is set up. #258: USB identity joins
discovery, so an unknown instrument is named instead of ignored, and a
software MIDI port is never mistaken for a device."""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
import test_device_catalog as tdc
from devices import catalog, usb


@pytest.fixture(autouse=True)
def _the_one_as_an_unknown_device(monkeypatch):
    """These tests were written with the ToneX One as their unknown USB
    instrument, using its real descriptor. It is a known device since #334;
    its catalog entry is hidden here so the descriptor keeps testing the
    unknown-device path it was read off the unit for."""
    real = catalog.load
    monkeypatch.setattr(catalog, "load",
                        lambda: tuple(e for e in real() if e["kind"] != "tonex_one"))

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "ioreg_tonex_one.plist"
#: The ToneX One as read off the real unit (#258): USB audio, CDC serial,
#: no MIDI streaming interface.
ONE = {"vid": 0x1963, "pid": 0x00d1, "maker": "IK Multimedia", "product": "ToneX One",
       "interfaces": [(1, 1), (1, 2), (2, 2), (10, 0)], "serial_port": "/dev/cu.usbmodem3101"}
PEDAL = {"vid": 0x1963, "pid": 0x0068, "maker": "IK Multimedia", "product": "ToneX",
         "interfaces": [(1, 1), (1, 2), (1, 3), (2, 2), (10, 0)], "serial_port": "/dev/cu.usbmodem1"}
SYNTH = {"vid": 0x1234, "pid": 0x0001, "maker": "Acme", "product": "Acme Synth",
         "interfaces": [(1, 1), (1, 3)], "serial_port": None}
KEYBOARD = {"vid": 0x05ac, "pid": 0x0250, "maker": "Apple", "product": "Keyboard",
            "interfaces": [(3, 1)], "serial_port": None}
REAL_DETECTED = tdc.REAL_DETECTED
#: captured at import, before conftest switches USB discovery off
REAL_LIST_USB = usb.list_usb


# -- #259: the bus watcher is live before the first request ------------------------------

@pytest.fixture
def fresh_watch(monkeypatch):
    state = {"on": False, "cb": None, "ready": threading.Event(), "ok": None}
    monkeypatch.setattr(server, "_coremidi_watch", state)
    monkeypatch.setattr(server, "_is_macos", lambda: True)
    return state


def _fake_pump(state, delay, ok):
    def pump():
        if state["on"]:
            return
        state["on"] = True

        def run():
            if delay is None:
                return                      # never ready
            time.sleep(delay)
            state["ok"] = ok
            state["ready"].set()
        threading.Thread(target=run, daemon=True).start()
    return pump


def test_watch_startup_waits_until_the_client_exists(monkeypatch, fresh_watch):
    monkeypatch.setattr(server, "_pump_coremidi", _fake_pump(fresh_watch, 0.3, True))
    seen = []
    monkeypatch.setattr(server, "detected_devices", lambda: seen.append(fresh_watch["ok"]) or [])
    with TestClient(server.app) as client:
        # ok is only set after the delayed client exists, so startup waited
        # (an elapsed-time check flaked on Windows' coarse clock)
        assert fresh_watch["ok"] is True
        assert client.get("/api/state").status_code == 200
    assert seen and all(ok is True for ok in seen)   # no enumeration before readiness


def test_watch_failure_still_lets_the_app_start(monkeypatch, fresh_watch, caplog):
    monkeypatch.setattr(server, "_pump_coremidi", _fake_pump(fresh_watch, 0.0, False))
    with TestClient(server.app) as client:
        assert client.get("/api/state").status_code == 200
    assert any("could not start" in r.message for r in caplog.records)


def test_watch_timeout_is_bounded_and_tolerated(monkeypatch, fresh_watch, caplog):
    monkeypatch.setattr(server, "_pump_coremidi", _fake_pump(fresh_watch, None, True))
    t0 = time.monotonic()
    assert server.start_bus_watch(timeout=0.2) is False
    assert time.monotonic() - t0 < 1.0
    assert any("not ready" in r.message for r in caplog.records)


def test_watch_is_a_no_op_off_macos(monkeypatch, fresh_watch):
    monkeypatch.setattr(server, "_is_macos", lambda: False)
    monkeypatch.setattr(server, "_pump_coremidi", lambda: pytest.fail("pumped off macOS"))
    assert server.start_bus_watch() is False


def test_watch_main_starts_it_too(monkeypatch):
    # main() pushes the saved AI settings into os.environ; doing that for
    # real here leaked into later tests in the same process (CI shard 0)
    monkeypatch.setattr(server.ai_settings, "apply_to_env", lambda *a, **k: None)
    calls = []
    monkeypatch.setattr(server, "start_bus_watch", lambda *a, **k: calls.append("watch"))
    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: calls.append("serve"))
    server.main()
    assert calls[:1] == ["watch"] and "serve" in calls


@pytest.mark.skipif(sys.platform != "darwin", reason="CoreMIDI is macOS only")
def test_watch_real_watcher_waits_for_a_delayed_client(monkeypatch, fresh_watch):
    real = server._coremidi_create_client

    def slow(*args):
        time.sleep(0.3)
        return real(*args)
    monkeypatch.setattr(server, "_coremidi_create_client", slow)
    t0 = time.monotonic()
    assert server.start_bus_watch(timeout=2.0) is True
    assert time.monotonic() - t0 >= 0.3


# -- #260: the ToneX Pedal -------------------------------------------------------------

def test_tonex_pedal_recognised_by_name_and_by_usb():
    assert [d["kind"] for d in catalog.recognise(["ToneX"])] == ["tonex"]
    assert [d["kind"] for d in catalog.recognise([], [PEDAL])] == ["tonex"]


@pytest.mark.parametrize("names,devices", [(["ToneX One"], []), ([], [ONE]),
                                           (["ToneX One"], [ONE]), (["ToneXtra"], [])])
def test_tonex_never_matches_a_tonex_one(names, devices):
    assert "tonex" not in [d["kind"] for d in catalog.recognise(names, devices)]


@pytest.mark.parametrize("configured", [False, True])
def test_tonex_supported_follows_configuration_without_recursion(monkeypatch, configured):
    monkeypatch.setattr(server, "detected_devices", REAL_DETECTED)
    monkeypatch.setattr(server, "available_devices",
                        lambda: pytest.fail("discovery asked available_devices"))
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: ["ToneX"])
    monkeypatch.delenv("TONECOMMAND_TONEX_PORT", raising=False)
    if configured:
        monkeypatch.setenv("TONECOMMAND_TONEX_SIM", "1")
    else:
        monkeypatch.delenv("TONECOMMAND_TONEX_SIM", raising=False)
    tonex = [d for d in server.detected_devices() if d["kind"] == "tonex"]
    assert tonex and tonex[0]["supported"] is configured
    assert tonex[0]["issue"] == 27


def test_tonex_unconfigured_card_says_not_yet_and_never_connects(tmp_path):
    entry = dict(catalog.recognise(["ToneX"])[0], supported=False)
    r = tdc._card(tmp_path, lists=[[tdc.FM9], [tdc.FM9, entry]])
    assert not [c for c in r["calls"] if c[0] in ("select", "reconnect")]
    card = [p for p in r["paints"] if p][-1]
    assert card["text"] == "ToneCommand cannot control it yet."
    assert card["issue_url"].endswith("/27")


# -- #258: USB identity and unknown instruments ------------------------------------------

def test_usb_reads_the_tonex_ones_real_tree():
    devices = usb.parse_ioreg(FIXTURE.read_bytes())
    assert devices == [dict(ONE, interfaces=sorted(ONE["interfaces"]))]
    assert "serial" not in json.dumps(devices).lower().replace("serial_port", "")


def test_usb_hub_does_not_inherit_its_downstream_devices():
    """A hub's subtree holds the devices plugged into it; their interfaces
    and serial ports stay theirs (ioreg lists each device on its own too)."""
    import plistlib
    synth = {"idVendor": 0x1234, "idProduct": 1, "USB Vendor Name": "Acme", "USB Product Name": "Acme Synth",
             "IORegistryEntryChildren": [
                 {"bInterfaceClass": 1, "bInterfaceSubClass": 3,
                  "IORegistryEntryChildren": [{"IOCalloutDevice": "/dev/cu.usbmodem9"}]}]}
    hub = {"idVendor": 0x05e3, "idProduct": 0x0610, "USB Vendor Name": "Generic", "USB Product Name": "USB2.0 Hub",
           "IORegistryEntryChildren": [{"bInterfaceClass": 9, "bInterfaceSubClass": 0,
                                        "IORegistryEntryChildren": [synth]}]}
    got = usb.parse_ioreg(plistlib.dumps([hub, synth]))
    assert got[0]["product"] == "USB2.0 Hub"
    assert got[0]["interfaces"] == [(9, 0)] and got[0]["serial_port"] is None
    assert got[1]["interfaces"] == [(1, 3)] and got[1]["serial_port"] == "/dev/cu.usbmodem9"
    assert [d["kind"] for d in catalog.unrecognised([], got, profiles={})] == ["usb:1234:0001"]


@pytest.mark.skipif(sys.platform == "win32", reason="sysfs names hold ':', which Windows paths cannot")
def test_usb_reads_linux_sysfs(tmp_path):
    dev = tmp_path / "1-2"
    dev.mkdir()
    for name, value in (("idVendor", "1963"), ("idProduct", "00d1"),
                        ("manufacturer", "IK Multimedia"), ("product", "ToneX One"),
                        ("serial", "SECRET123")):
        (dev / name).write_text(value + "\n", encoding="utf-8")
    for n, (c, s) in enumerate([("01", "01"), ("02", "02"), ("0a", "00")]):
        itf = dev / f"1-2:1.{n}"
        itf.mkdir()
        (itf / "bInterfaceClass").write_text(c, encoding="utf-8")
        (itf / "bInterfaceSubClass").write_text(s, encoding="utf-8")
    (dev / "1-2:1.2" / "tty").mkdir()
    (dev / "1-2:1.2" / "tty" / "ttyACM0").mkdir()
    (tmp_path / "usb1").mkdir()                       # a root hub without IDs is skipped
    got = usb.read_sysfs(tmp_path)
    assert got == [{"vid": 0x1963, "pid": 0xd1, "maker": "IK Multimedia", "product": "ToneX One",
                    "interfaces": [(1, 1), (2, 2), (10, 0)], "serial_port": "/dev/ttyACM0"}]
    assert "SECRET" not in json.dumps(got)


def test_usb_list_is_cached_fresh_on_demand_and_never_raises(monkeypatch):
    reads = []
    monkeypatch.setattr(usb, "_cache", {"at": 0.0, "devices": None})
    monkeypatch.setattr(usb, "list_usb", REAL_LIST_USB)
    monkeypatch.setattr(usb, "_read", lambda: reads.append(1) or [ONE])
    assert usb.list_usb(now=100.0) == [ONE] and usb.list_usb(now=101.0) == [ONE]
    assert len(reads) == 1
    usb.list_usb(now=101.5, fresh=True)
    usb.list_usb(now=110.0)
    assert len(reads) == 3
    monkeypatch.setattr(usb, "_read", lambda: 1 / 0)
    assert usb.list_usb(now=200.0) == []


def test_unknown_instrument_is_listed_by_maker():
    got = catalog.unrecognised(["EZdrummer 3"], [ONE, KEYBOARD], profiles={})
    assert got == [{"kind": "usb:1963:00d1", "label": "IK Multimedia ToneX One", "supported": False,
                    "verified": False, "issue": 239,
                    "issue_url": "https://github.com/monzta1/ToneCommand/issues/239",
                    "read_only": False, "unknown": True, "learned": False}]


def test_unknown_software_port_is_never_a_device():
    assert catalog.unrecognised(["EZdrummer 3", "IAC Driver Bus 1"], [KEYBOARD], profiles={}) == []


def test_unknown_virtual_port_named_like_a_device_is_not_its_port():
    """The review's collision: a virtual 'ToneX One' port with the real One
    plugged in. The One has no MIDI streaming interface, so no port is its."""
    assert catalog.owned_ports(ONE, ["ToneX One", "ToneX One 2"], [ONE]) == []


def test_unknown_midi_device_owns_only_an_unambiguous_port():
    twin = dict(SYNTH, pid=0x0002)
    assert catalog.owned_ports(SYNTH, ["Acme Synth MIDI 1", "EZdrummer 3"], [SYNTH]) == ["Acme Synth MIDI 1"]
    assert catalog.owned_ports(SYNTH, ["Acme Synth MIDI 1"], [SYNTH, twin]) == []
    assert [d["kind"] for d in catalog.unrecognised(["Acme Synth MIDI 1"], [SYNTH], profiles={})] == \
        ["usb:1234:0001"]


def test_unknown_skips_devices_the_catalog_knows():
    assert catalog.unrecognised(["ToneX"], [PEDAL], profiles={}) == []


def test_unknown_reaches_the_state_through_discovery(monkeypatch):
    monkeypatch.setattr(server, "detected_devices", REAL_DETECTED)
    monkeypatch.setattr(usb, "list_usb", lambda *a, **k: [ONE, KEYBOARD])
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: ["EZdrummer 3"])
    kinds = [d["kind"] for d in server.detected_devices()]
    assert kinds == ["usb:1963:00d1"]


HARNESS = """
import { readFileSync } from "node:fs";
const src = readFileSync(process.argv[2], "utf8");
const start = src.indexOf(process.argv[3]);
const end = src.indexOf(process.argv[4], start);
const code = src.slice(start, end);
const sc = JSON.parse(process.argv[5]);
const $ = () => ({ dataset: {}, style: {}, querySelector: () => ({ style: {} }) });
const api = new Function("$", "sessionStorage", "deviceGen", "deviceState", "fetch", "refresh", "setTimeout",
  code + "\\nreturn {unsupportedCard, learnDevice};")($, null, 0, {}, null, null, null);
const paints = [], posts = [];
const out = { cards: (sc.cards || []).map(api.unsupportedCard) };
if (sc.learn) {
  out.result = await api.learnDevice(sc.learn, { paint: st => paints.push(st),
    post: async body => { posts.push(body); return { status: 200, d: sc.reply }; } });
}
console.log(JSON.stringify(Object.assign(out, { paints, posts })));
"""


def _page(tmp_path, **scenario):
    h = tmp_path / "learn.mjs"
    h.write_text(HARNESS, encoding="utf-8")
    out = subprocess.run(["node", str(h), str(ROOT / "ui" / "index.html"), tdc.START, tdc.END,
                          json.dumps(scenario)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_card_names_an_unknown_device_and_offers_to_learn(tmp_path):
    entry = catalog.unrecognised([], [ONE], profiles={})[0]
    learned = dict(entry, unknown=False, learned=True, known=["USB audio: 2 in, 2 out, 44100 Hz", "No MIDI port"])
    r = _page(tmp_path, cards=[entry, learned])
    unknown, done = r["cards"]
    assert unknown["title"] == "IK Multimedia ToneX One found" and unknown["learn"] is True
    assert unknown["text"] == "ToneCommand doesn't know it yet. Learning it only listens: nothing is sent to it."
    assert done["title"] == "Learned: IK Multimedia ToneX One" and not done.get("learn")
    assert done["text"] == "Known: USB audio: 2 in, 2 out, 44100 Hz; No MIDI port."
    assert 'id="devcardlearn"' in tdc.PAGE


def test_card_learn_posts_consent_and_shows_what_is_known(tmp_path):
    reply = {"ok": True, "profile": {"label": "IK Multimedia ToneX One", "known": ["No MIDI port"]}}
    r = _page(tmp_path, learn="usb:1963:00d1", reply=reply)
    assert r["posts"] == [{"kind": "usb:1963:00d1", "consent": True}]
    assert r["result"] == "learned"
    assert r["paints"][0]["text"].endswith("Nothing is sent to it.")
    assert r["paints"][-1]["title"] == "Learned: IK Multimedia ToneX One"



# -- #263: USB identity on Windows ------------------------------------------------------

WIN_ROWS = [
    # a ToneX One-like composite device: the parent names it, MI_nn interfaces
    # give classes, a Ports interface gives the COM port; the instance after
    # the last backslash is a serial number and must never come through
    {"PNPDeviceID": "USB\\VID_1963&PID_00D1\\SECRET123", "Name": "ToneX One", "Manufacturer": "IK Multimedia",
     "PNPClass": "USB", "CompatibleID": ["USB\\DevClass_EF&SubClass_02&Prot_01", "USB\\COMPOSITE"]},
    {"PNPDeviceID": "USB\\VID_1963&PID_00D1&MI_00\\7&ABC&0&0000", "Name": "USB Serial Device (COM5)",
     "Manufacturer": "Microsoft", "PNPClass": "Ports", "CompatibleID": ["USB\\Class_02&SubClass_02&Prot_01"]},
    {"PNPDeviceID": "USB\\VID_1963&PID_00D1&MI_02\\7&ABC&0&0002", "Name": "ToneX One",
     "Manufacturer": "(Generic USB Audio)", "PNPClass": "MEDIA", "CompatibleID": ["USB\\Class_01&SubClass_01&Prot_00"]},
    # a MIDI interface: one interface, MIDI streaming
    {"PNPDeviceID": "USB\\VID_1234&PID_0001\\5&XYZ", "Name": "Acme Synth", "Manufacturer": "Acme",
     "PNPClass": "MEDIA", "CompatibleID": ["USB\\Class_01&SubClass_03&Prot_00", "USB\\Class_01"]},
    # a hub, and a non-USB-ID entry that is skipped
    {"PNPDeviceID": "USB\\VID_05E3&PID_0610\\6&HUB", "Name": "Generic USB Hub", "Manufacturer": "(Standard USB HUBs)",
     "PNPClass": "USB", "CompatibleID": "USB\\Class_09&SubClass_00&Prot_02"},
    {"PNPDeviceID": "USB\\ROOT_HUB30\\4&1", "Name": "USB Root Hub", "PNPClass": "USB"},
]


def test_windows_reads_composite_midi_and_hub_devices():
    got = usb.parse_windows(json.dumps(WIN_ROWS))
    assert got == [
        {"vid": 0x05e3, "pid": 0x0610, "maker": "(Standard USB HUBs)", "product": "Generic USB Hub",
         "interfaces": [(9, 0)], "serial_port": None},
        {"vid": 0x1234, "pid": 0x0001, "maker": "Acme", "product": "Acme Synth",
         "interfaces": [(1, 3)], "serial_port": None},
        {"vid": 0x1963, "pid": 0x00d1, "maker": "IK Multimedia", "product": "ToneX One",
         "interfaces": [(1, 1), (2, 2)], "serial_port": "COM5"}]
    text = json.dumps(got)
    assert "SECRET" not in text and "XYZ" not in text and "7&ABC" not in text
    kinds = [d["kind"] for d in catalog.unrecognised([], got, profiles={})]
    assert kinds == ["usb:1234:0001", "usb:1963:00d1"]       # the hub is no instrument


@pytest.mark.parametrize("text", ["", "not json", "{}", "[1, 2]", json.dumps(WIN_ROWS[0])])
def test_windows_parser_tolerates_odd_output(text):
    try:
        got = usb.parse_windows(text)
    except ValueError:
        got = None
    assert got is None or isinstance(got, list)
    if text == json.dumps(WIN_ROWS[0]):
        assert got[0]["product"] == "ToneX One" and got[0]["interfaces"] == []


def test_windows_list_usb_dispatches_and_never_raises(monkeypatch):
    monkeypatch.setattr(usb, "list_usb", REAL_LIST_USB)
    monkeypatch.setattr(usb, "_cache", {"at": 0.0, "devices": None})
    monkeypatch.setattr(usb.sys, "platform", "win32")
    monkeypatch.setattr(usb, "read_windows", lambda: usb.parse_windows(json.dumps(WIN_ROWS)))
    assert [d["product"] for d in usb.list_usb(fresh=True)] == ["Generic USB Hub", "Acme Synth", "ToneX One"]
    monkeypatch.setattr(usb, "read_windows", lambda: usb.parse_windows("not json"))
    assert usb.list_usb(fresh=True) == []


@pytest.mark.skipif(sys.platform != "win32", reason="the real Windows reader runs on Windows only")
def test_windows_real_reader_runs_on_this_machine():
    """#263 REQ-004: the CI Windows runner reads its own USB tree. The command
    itself must succeed: an empty list from a failing command proves nothing."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", usb.PS_COMMAND],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and not r.stderr.strip(), r.stderr
    assert usb.parse_windows(r.stdout) is not None
    got = usb.read_windows()
    assert isinstance(got, list)
    for d in got:
        assert set(d) == {"vid", "pid", "maker", "product", "interfaces", "serial_port"}
    # a warning, so CI's quiet run still shows the read happened (evidence for #263)
    import warnings
    warnings.warn(f"#263 real Windows USB read: powershell exit {r.returncode}, "
                  f"{len(r.stdout)} bytes, {len(got)} device(s): "
                  f"{[(hex(d['vid']), hex(d['pid']), d['product']) for d in got]}")
