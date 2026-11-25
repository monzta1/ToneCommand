"""#261: the first DDLP slice. A consented probe that sends nothing turns an
unknown device into a profile, and the profile makes it recognised."""
import json
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
import test_device_discovery as tdd
from devices import catalog, ddlp, usb

ONE, SYNTH, KEYBOARD = tdd.ONE, tdd.SYNTH, tdd.KEYBOARD
AUDIO = {"inputs": 2, "outputs": 2, "sample_rate": 44100}


@pytest.fixture(autouse=True)
def _the_one_as_an_unknown_device(monkeypatch):
    """These tests were written with the ToneX One as their unknown USB
    instrument, using its real descriptor. It is a known device since #334;
    its catalog entry is hidden here so the descriptor keeps testing the
    unknown-device path it was read off the unit for."""
    real = catalog.load
    monkeypatch.setattr(catalog, "load",
                        lambda: tuple(e for e in real() if e["kind"] != "tonex_one"))


class Port:
    def __init__(self, name, pending=()):
        self.name, self.pending, self.closed = name, list(pending), False

    def iter_pending(self):
        out, self.pending = self.pending, []
        return out

    def close(self):
        self.closed = True


class Msg:
    def __init__(self, raw):
        self.raw = raw

    def hex(self):
        return self.raw


def no_open(name):
    raise AssertionError(f"the probe opened {name!r}")


def run(kind="usb:1963:00d1", ins=(), outs=(), devices=(ONE,), open_input=no_open, audio=AUDIO):
    return ddlp.probe(kind, port_names=list(ins), out_names=list(outs), usb_devices=list(devices),
                      open_input=open_input, audio_reader=lambda product: audio, seconds=0.1)


@pytest.fixture(autouse=True)
def nothing_sent(monkeypatch):
    """Any MIDI output or serial open during a probe fails the test."""
    import mido
    monkeypatch.setattr(mido, "open_output", lambda *a, **k: pytest.fail("MIDI output opened"))
    monkeypatch.setattr(mido, "open_ioport", lambda *a, **k: pytest.fail("MIDI io port opened"))
    import builtins
    real_open = builtins.open

    def guarded(file, *a, **k):
        if str(file).startswith("/dev/"):
            pytest.fail(f"device node opened: {file}")
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", guarded)
    import os
    real_os_open = os.open
    monkeypatch.setattr(os, "open", lambda path, *a, **k: pytest.fail(f"opened {path}")
                        if str(path).startswith("/dev/") else real_os_open(path, *a, **k))


def test_probe_profiles_the_tonex_one_and_sends_nothing():
    prof = run()
    assert ddlp.validate(prof) == []
    assert prof["id"] == "ik-multimedia-tonex-one" and prof["label"] == "IK Multimedia ToneX One"
    assert prof["identity"]["vid"] == 0x1963 and prof["identity"]["pid"] == 0xd1
    t = prof["transports"]
    assert t["midi_in"]["value"] == [] and t["midi_out"]["value"] == []
    assert t["usb_audio"]["value"] == AUDIO and t["serial_control"]["value"] is True
    assert prof["probe"] == {"tool": ddlp.TOOL, "bytes_sent": 0, "listened_seconds": 0}
    assert prof["parameters"] == [] and prof["verified_writes"] == []
    assert prof["known"] == [
        "USB identity: IK Multimedia ToneX One (1963:00d1)",
        "USB audio: 2 in, 2 out, running at 44100 Hz",
        "Serial control port present (not opened, contents not read)",
        "No MIDI port",
        "No controls known yet: nothing can be changed from ToneCommand"]


def test_probe_never_takes_a_virtual_port_for_the_one():
    """A software port named 'ToneX One' is not the One's: no input opened."""
    prof = run(ins=["ToneX One"], outs=["ToneX One"])
    assert prof["transports"]["midi_in"]["value"] == [] and prof["observed"] == []


def test_probe_listens_only_on_the_devices_own_input():
    opened = []

    def open_input(name):
        opened.append(name)
        return Port(name, [Msg("f0 7e 00 f7"), Msg("b0 07 64")])
    prof = run(kind="usb:1234:0001", ins=["Acme Synth MIDI 1", "EZdrummer 3"],
               outs=["Acme Synth MIDI 1"], devices=[SYNTH], open_input=open_input, audio=None)
    assert opened == ["Acme Synth MIDI 1"]
    assert [o["message"] for o in prof["observed"]] == ["f0 7e 00 f7", "b0 07 64"]
    assert all(o["provenance"]["kind"] == "observed" for o in prof["observed"])
    assert prof["transports"]["midi_out"]["value"] == ["Acme Synth MIDI 1"]   # named, never opened
    assert ddlp.validate(prof) == []


@pytest.mark.parametrize("kind,devices", [("usb:dead:beef", [ONE]), ("usb:05ac:0250", [KEYBOARD]),
                                          ("usb:1963:00d1", [])])
def test_probe_refuses_what_is_not_an_unknown_instrument(kind, devices):
    with pytest.raises(ddlp.ProbeRefused):
        run(kind=kind, devices=devices)


def test_profile_validation_catches_missing_provenance_serials_and_sends():
    good = run()
    assert ddlp.validate(dict(good, probe=dict(good["probe"], bytes_sent=3)))
    bad = json.loads(json.dumps(good))
    del bad["transports"]["usb_audio"]["provenance"]
    assert ddlp.validate(bad)
    leak = json.loads(json.dumps(good))
    leak["identity"]["serial_number"] = "X"
    assert ddlp.validate(leak)
    assert ddlp.validate({"schema": 1}) == ["missing id", "missing label", "missing identity",
                                            "missing transports", "missing observed",
                                            "missing parameters", "missing verified_writes",
                                            "missing known", "missing probe"]


def test_saved_profile_makes_the_device_learned(tmp_path):
    path = ddlp.save(run(), tmp_path / "learned")
    assert path.name == "ik-multimedia-tonex-one.json"
    profiles = catalog.load_profiles([tmp_path / "learned"])
    got = catalog.unrecognised([], [ONE], profiles=profiles)
    assert got[0]["learned"] is True and got[0]["unknown"] is False
    assert got[0]["known"][0] == "USB identity: IK Multimedia ToneX One (1963:00d1)"


def test_reviewed_profile_wins_over_a_learned_copy(tmp_path):
    reviewed, learned = tmp_path / "profiles", tmp_path / "learned"
    ddlp.save(dict(run(), label="Reviewed One"), reviewed)
    ddlp.save(dict(run(), label="Local One"), learned)
    (learned / "broken.json").write_text("{not json", encoding="utf-8")
    prof = catalog.load_profiles([reviewed, learned])[(0x1963, 0xd1)]
    assert prof["label"] == "Reviewed One" and prof["reviewed"] is True


def test_committed_profiles_are_valid():
    for f in sorted((catalog.DEVICES_DIR / "profiles").glob("*.json")):
        assert ddlp.validate(json.loads(f.read_text(encoding="utf-8"))) == [], f.name


# -- the route ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(usb, "list_usb", lambda *a, **k: [ONE])
    monkeypatch.setattr(ddlp, "LEARNED_DIR", tmp_path / "learned")
    monkeypatch.setattr(ddlp, "read_usb_audio", lambda product: AUDIO)
    from fm9 import midi_transport
    monkeypatch.setattr(midi_transport, "port_names", lambda *a, **k: ["EZdrummer 3"])
    monkeypatch.setattr(midi_transport, "output_names", lambda *a, **k: [])
    return TestClient(server.app), tmp_path / "learned"


@pytest.mark.parametrize("consent", [None, False, "yes", 1])
def test_route_refuses_without_consent(client, consent):
    c, learned = client
    r = c.post("/api/ddlp/probe", json={"kind": "usb:1963:00d1", "consent": consent})
    assert r.status_code == 400 and not learned.exists()


def test_route_learns_with_consent(client):
    c, learned = client
    r = c.post("/api/ddlp/probe", json={"kind": "usb:1963:00d1", "consent": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["saved"] == "ik-multimedia-tonex-one.json"
    assert body["profile"]["probe"]["bytes_sent"] == 0
    assert json.loads((learned / body["saved"]).read_text(encoding="utf-8"))["id"] == "ik-multimedia-tonex-one"


def test_route_refuses_an_unknown_kind(client):
    c, learned = client
    r = c.post("/api/ddlp/probe", json={"kind": "usb:0000:0000", "consent": True})
    assert r.status_code == 400 and not learned.exists()
