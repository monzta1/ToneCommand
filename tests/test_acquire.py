""""Get me the Periphery tones from Gift of Tone", as a sentence. Issue #42.

The catalog match is deterministic (no model in the loop), the download is
validated file by file by the same parser as a dropped .syx, and nothing
reaches flash except through /api/install with its whitelist, gig lock and
read-back. CI never touches the network: fetches are injected.
"""
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import acquire
from tests.test_install import make_file

UI = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()

HTML = """
<a href="https://www.fractalaudio.com/downloads/misc/_gift24/FAS-gift24-01-Periphery.zip">x</a>
<a href="https://www.fractalaudio.com/downloads/misc/_gift22/FAS-gift22-16-Steve-Vai.zip">x</a>
<a href="https://www.fractalaudio.com/downloads/misc/_gift22/FAS-gift22-22-John-Petrucci.zip">x</a>
<a href="https://www.fractalaudio.com/downloads/misc/_gift22/FAS-gift22-16-Steve-Vai.zip">dupe</a>
"""


def test_the_catalog_reads_artists_out_of_the_urls():
    entries = acquire.catalog(fetch=lambda url: HTML.encode())
    assert [e["artist"] for e in entries][:1] == ["Periphery"]
    assert {e["artist"] for e in entries} == \
        {"Periphery", "Steve Vai", "John Petrucci"}
    assert entries[0]["year"] == 2024


def test_the_ask_matches_deterministically():
    entries = acquire.catalog(fetch=lambda url: HTML.encode())
    hit = acquire.find("get me the periphery tones from gift of tone", entries)
    assert hit["artist"] == "Periphery"
    assert acquire.find("grab steve vai", entries)["artist"] == "Steve Vai"
    # every meaningful word must match: nobody gets a wrong artist "close
    # enough" to overwrite a slot with
    assert acquire.find("get the meshuggah tones from gift of tone",
                        entries) is None


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()


def test_a_bundle_yields_fm9_presets_and_honest_skips():
    data = _zip([
        ("FM9/Misha GoTFM9.syx", make_file(name="Misha GoT")),
        ("FM3/Misha GoTFM3.syx", make_file(name="Misha GoT", model=0x11)),
        ("FM9/._Misha GoTFM9.syx", b"\x00\x05junk"),   # AppleDouble
        ("_ReadMe.txt", b"enjoy"),
    ])
    presets, skipped = acquire.fetch_presets("http://x/bundle.zip",
                                             fetch=lambda url: data)
    assert [p["name"] for p in presets] == ["Misha GoT"]
    assert len(skipped) == 1 and "FM3" in skipped[0]


def test_a_bundle_with_no_fm9_presets_says_so():
    data = _zip([("only.syx", make_file(model=0x10))])
    with pytest.raises(acquire.AcquireError, match="no FM9 presets"):
        acquire.fetch_presets("http://x/b.zip", fetch=lambda url: data)


# --- the sentence, end to end against the simulator -----------------------

@pytest.fixture
def client(monkeypatch):
    from fm9.sim import SimFM9
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    monkeypatch.setattr(server, "_gig_mode", {"on": False})
    monkeypatch.setattr(server, "_install_cache", {})
    monkeypatch.setattr(server, "_preset_cache", {"slots": None})
    return TestClient(server.app)


def test_the_sentence_becomes_installable_presets(client, monkeypatch):
    bundle = _zip([("FM9/Misha GoTFM9.syx", make_file(name="Misha GoT"))])
    def fake_download(url):
        return HTML.encode() if "gift-of-tone" in url else bundle
    monkeypatch.setattr(acquire, "_download", fake_download)
    d = client.post("/api/acquire", json={
        "query": "get me the periphery tones from gift of tone"}).json()
    assert d["artist"] == "Periphery"
    assert [p["name"] for p in d["presets"]] == ["Misha GoT"]
    # and the found preset installs through the guarded path, read back
    out = client.post("/api/install", json={
        "hash": d["presets"][0]["hash"], "slot": 140}).json()
    assert out["ok"] is True and out["read_back"] == "Misha GoT"


def test_an_unmatched_ask_names_recent_gifts(client, monkeypatch):
    monkeypatch.setattr(acquire, "_download", lambda url: HTML.encode())
    r = client.post("/api/acquire", json={
        "query": "get the meshuggah tones from gift of tone"})
    assert r.status_code == 404
    assert "Periphery" in r.json()["error"]


def test_the_composer_routes_a_named_source_to_acquire():
    script = UI.split("<script>")[1]
    assert "function acquireIntent" in script
    fn = script.split("async function talk() {")[1].split("chatBusy = true")[0]
    assert "acquireIntent(said)" in fn and "runAcquire(said)" in fn
    # Only a NAMED source intercepts; a plain tone request still converses.
    assert "gift\\s*of\\s*tone" in script
