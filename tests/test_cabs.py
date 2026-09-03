"""User-cab (IR) installs: issue #42 phase 4, the step players get wrong.

An artist bundle's IRs must land in the user-cab slots the presets
reference. Fractal's own export naming (U{n}-...) states that slot; the
default destination honors it. Layout verified against a real artist
export (Wes Hauch GoT 2023: 0x7A + 8x1290 0x7B + 0x7C, Axe-III model
byte); the write direction, model rewrite and slot addressing remain
hardware-unverified and everything says so.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import acquire, cabfile, protocol as p
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def make_cab(model=0x10, chunks=8, chunk_len=1282):
    frames = [p.envelope(0x7A, [0x7F, 0x7F, 0x00, 0x10, 0x7F], model=model)]
    for i in range(chunks):
        frames.append(p.envelope(0x7B, [i, 0] + [j & 0x7F for j in
                                                 range(chunk_len)],
                                 model=model))
    frames.append(p.envelope(0x7C, [1, 2, 3, 4, 5], model=model))
    return bytes(b for f in frames for b in f)


def test_a_cab_file_parses_whatever_gen3_device_exported_it():
    cf = cabfile.parse(make_cab(model=0x10), "U3-Cab_Big Room.syx")
    assert cf.source_model == 0x10
    assert cf.chunks == 8
    assert cf.label == "Big Room"


def test_the_artists_filing_is_the_default_slot():
    assert cabfile.default_slot("U1-Cab_Wes_Rhythm Match.syx") == 0
    assert cabfile.default_slot("U16-something.syx") == 15
    assert cabfile.default_slot("just-a-cab.syx") is None


def test_retarget_rewrites_model_and_slot_with_valid_checksums():
    cf = cabfile.parse(make_cab(model=0x10), "U1-x.syx")
    frames = cabfile.retarget(cf, 4)
    assert all(f[4] == p.MODEL_FM9 for f in frames)
    assert ((frames[0][6] << 7) | frames[0][7]) == 4
    assert all(p.checksum(f[1:-2]) == f[-2] for f in frames)


def test_a_corrupt_cab_is_refused():
    raw = bytearray(make_cab())
    raw[30] ^= 0x01
    with pytest.raises(cabfile.CabFileError, match="checksum"):
        cabfile.parse(bytes(raw), "U1-x.syx")


def test_the_cab_family_is_not_on_the_main_send_surface():
    from fm9.device import FM9
    for fn in (0x19, 0x7A, 0x7B, 0x7C):
        assert fn not in FM9.SENDABLE_FNS


# --- the whole road on the simulator --------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_CAB_SLOTS", "0-15")
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_install_cache", {})
    return TestClient(server.app)


def _stage(client, raw):
    import hashlib
    digest = hashlib.sha1(raw).hexdigest()
    server._install_cache[digest] = raw
    return digest


def test_install_ir_and_read_back_byte_identical(client):
    h = _stage(client, make_cab())
    out = client.post("/api/install-cab",
                      json={"hash": h, "slot": 0,
                            "filename": "U1-Cab_Test.syx"}).json()
    assert out["ok"] is True and out["user_cab"] == 1
    assert "byte-identical" in out["detail"]
    assert any("user-cab install" in u
               for u in server._fm9.sim_core.undecoded)


def test_cab_install_refused_outside_the_cab_whitelist(client):
    h = _stage(client, make_cab())
    r = client.post("/api/install-cab", json={"hash": h, "slot": 500})
    assert r.status_code == 403


def test_cab_install_disabled_without_a_whitelist(client, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_CAB_SLOTS", "")
    h = _stage(client, make_cab())
    r = client.post("/api/install-cab", json={"hash": h, "slot": 0})
    assert r.status_code == 403
    assert "TONECOMMAND_CAB_SLOTS" in r.json()["error"]


def test_a_bundle_yields_cabs_beside_presets():
    from tests.test_install import make_file
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("FM9/preset.syx", make_file(name="With IR"))
        z.writestr("Cabs/U2-Cab_Room.syx", make_cab())
    presets, cabs, skipped = acquire.fetch_bundle(
        "http://x/b.zip", fetch=lambda url: buf.getvalue())
    assert [pr["name"] for pr in presets] == ["With IR"]
    assert cabs[0]["label"] == "Room" and cabs[0]["default_slot"] == 1
    assert skipped == []


def test_the_page_offers_ir_rows_with_the_artists_slot():
    assert "INSTALL IR" in UI
    assert "/api/install-cab" in UI
    assert "the artist filed this for User Cab" in UI
