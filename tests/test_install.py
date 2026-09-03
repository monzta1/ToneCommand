"""Installing preset files (.syx) to whitelisted slots. Issue #42.

The parser trusts nothing: every frame checksummed, the envelope shape
enforced, the model byte matched, the name magic required. The device path
sends only what the parser passed, through its own guard that admits only
the dump family, and the endpoint claims done only after the slot's name
reads back. The host-to-device direction is hardware-unverified protocol,
and everything here says so.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import presetfile, protocol as p
from fm9.sim import SimFM9

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()


def _words_chunk(name="GoT Petty", discrim=(0, 0)):
    words = [0] * 1024
    words[presetfile.NAME_MAGIC_WORD] = presetfile.NAME_MAGIC
    raw = name.encode()
    for i in range(presetfile.NAME_MAX_WORDS):
        lo = raw[2 * i] if 2 * i < len(raw) else 0
        hi = raw[2 * i + 1] if 2 * i + 1 < len(raw) else 0
        words[presetfile.NAME_FIRST_WORD + i] = lo | (hi << 8)
    body = []
    for w in words:
        body += [w & 0x7F, (w >> 7) & 0x7F, (w >> 14) & 0x03]
    return [*discrim, *body]


def make_file(name="GoT Petty", slot=273, chunks=8, model=p.MODEL_FM9):
    frames = [p.envelope(0x77, [(slot >> 7) & 0x7F, slot & 0x7F,
                                0x00, 0x40, 0x00], model=model)]
    for i in range(chunks):
        payload = _words_chunk(name if i == 0 else "", discrim=(i, 0))
        frames.append(p.envelope(0x78, payload, model=model))
    frames.append(p.envelope(0x79, [1, 2, 3], model=model))
    return bytes(b for f in frames for b in f)


# --- the parser trusts nothing --------------------------------------------

def test_a_valid_file_parses_with_its_name_and_source():
    pf = presetfile.parse(make_file())
    assert pf.name == "GoT Petty"
    assert pf.source_slot == 273
    assert pf.chunks == 8


def test_frame_lengths_match_the_documented_envelope():
    raw = make_file()
    frames = presetfile._split_frames(raw)
    assert len(frames[0]) == presetfile.HEADER_LEN == 13
    assert all(len(f) == presetfile.CHUNK_LEN == 3082 for f in frames[1:-1])
    assert len(frames[-1]) == presetfile.FOOTER_LEN == 11


def test_a_file_for_another_device_is_refused_by_name():
    with pytest.raises(presetfile.PresetFileError, match="Axe-Fx III"):
        presetfile.parse(make_file(model=0x10))
    with pytest.raises(presetfile.PresetFileError, match="FM3"):
        presetfile.parse(make_file(model=0x11))


def test_a_flipped_bit_is_refused_not_sent():
    raw = bytearray(make_file())
    raw[40] ^= 0x01
    with pytest.raises(presetfile.PresetFileError, match="checksum"):
        presetfile.parse(bytes(raw))


def test_a_truncated_file_is_refused():
    with pytest.raises(presetfile.PresetFileError, match="truncated"):
        presetfile.parse(make_file()[:-5])


def test_random_fractal_messages_are_not_a_preset():
    raw = bytes(p.envelope(0x0D, [0x00, 0x01]))
    with pytest.raises(presetfile.PresetFileError, match="not a preset dump"):
        presetfile.parse(raw)


def test_retarget_patches_the_header_only_and_stays_checksummed():
    pf = presetfile.parse(make_file(slot=273))
    frames = presetfile.retarget(pf, 140)
    head = frames[0]
    assert ((head[6] << 7) | head[7]) == 140
    assert p.checksum(head[1:-2]) == head[-2], "retarget must re-checksum"
    assert frames[1:] == [list(f) for f in pf.frames[1:]], \
        "chunks and footer travel verbatim, per the editor's own recipe"


# --- rule zero stays structural -------------------------------------------

def test_the_main_send_surface_did_not_widen():
    """0x77/0x78/0x79 are sendable only through install_preset's own guard;
    the ordinary transport refuses them exactly as before."""
    from fm9.device import FM9
    assert 0x77 not in FM9.SENDABLE_FNS
    assert 0x78 not in FM9.SENDABLE_FNS
    assert 0x79 not in FM9.SENDABLE_FNS


# --- the whole road, on the simulator -------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_install_cache", {})
    monkeypatch.setattr(server, "_preset_cache", {"slots": None})
    return TestClient(server.app)


def _b64(raw):
    import base64
    return base64.b64encode(raw).decode()


def test_parse_then_install_then_read_back(client):
    d = client.post("/api/install/parse",
                    json={"data": _b64(make_file())}).json()
    assert d["name"] == "GoT Petty" and d["chunks"] == 8
    out = client.post("/api/install",
                      json={"hash": d["hash"], "slot": 140}).json()
    assert out["ok"] is True
    assert out["read_back"] == "GoT Petty"
    assert "verified" in out["detail"]
    # And the sim confesses the direction is not hardware-proven.
    assert any("not" in u and "hardware" in u
               for u in server._fm9.sim_core.undecoded)


def test_install_refuses_a_slot_outside_the_whitelist(client):
    d = client.post("/api/install/parse",
                    json={"data": _b64(make_file())}).json()
    r = client.post("/api/install", json={"hash": d["hash"], "slot": 300})
    assert r.status_code == 403
    assert "refused" in r.json()["error"]


def test_gig_lock_refuses_the_flash_write(client, monkeypatch):
    d = client.post("/api/install/parse",
                    json={"data": _b64(make_file())}).json()
    monkeypatch.setattr(server, "_gig_mode", {"on": True})
    r = client.post("/api/install", json={"hash": d["hash"], "slot": 140})
    assert r.status_code == 423


def test_garbage_is_refused_at_the_door(client):
    r = client.post("/api/install/parse", json={"data": _b64(b"not sysex")})
    assert r.status_code == 422


def test_install_without_a_parse_is_refused(client):
    r = client.post("/api/install", json={"hash": "nope", "slot": 140})
    assert r.status_code == 409


def test_the_page_carries_the_install_flow():
    assert 'id="installfile"' in UI
    assert "INSTALL A PRESET FILE" in UI
    assert "/api/install/parse" in UI
    # The confirm names the destination and says flash, like every
    # irreversible act on this surface.
    assert "This writes flash. UNDO does not cover it." in UI
