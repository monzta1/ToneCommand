"""Issue #149 (I6, the intake half): one .nam, several, or a folder go
through I1, come back as one honest line each, are deduplicated by sha256,
grouped into sets of one amp and mapped to channels A to D or to scenes.
Nothing reaches the unit here.
"""
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import server
from fm9 import nam_intake
from fm9.sim import SimFM9
from tests.test_nam_intake import wavenet_doc

ROOT = Path(__file__).resolve().parent.parent
UI = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


def _nam(name, make="Friedman", model="BE-100", tone="hi_gain", gear_type="amp",
         by="X", **over):
    meta = {"name": name, "modeled_by": by, "gear_type": gear_type,
            "gear_make": make, "gear_model": model, "tone_type": tone,
            "date": {"year": 2026, "month": 9, "day": 19}}
    meta.update(over)
    return json.dumps(wavenet_doc(meta)).encode()


def _bare(name):
    return json.dumps(wavenet_doc(None, weights=[0.5, float(hash(name) % 7)])).encode()


# --- intake ------------------------------------------------------------------

def test_intake_single_file_describes_it_and_offers_nothing():
    r = nam_intake.intake([("be100 lead.nam", _nam("BE-100 lead"))])
    assert len(r.items) == 1 and r.sets == [] and len(r.singles) == 1
    it = r.items[0]
    assert it.record.gear == "Friedman BE-100"
    assert it.line.startswith("be100 lead.nam: capture of Friedman BE-100 by X; hi_gain; needs a cab")
    assert r.line.endswith("added to your library, say the word and I'll build with it")


def test_intake_honest_when_nothing_is_on_file():
    r = nam_intake.intake([("mystery.nam", _bare("m"))])
    assert "not on file" in r.items[0].line
    assert r.items[0].record.gear is None and r.sets == []


def test_intake_multiple_files_and_a_folder(tmp_path):
    d = tmp_path / "caps"
    (d / "sub").mkdir(parents=True)
    (d / "clean.nam").write_bytes(_nam("BE clean", tone="clean"))
    (d / "sub" / "crunch.nam").write_bytes(_nam("BE crunch", tone="crunch"))
    (d / "readme.txt").write_text("not a capture", encoding="utf-8")
    (d / "lead.nam").write_bytes(_nam("BE lead", tone="hi_gain"))
    r = nam_intake.intake([d, ("extra.nam", _nam("Other", make="Mesa", model="Mark IV"))])
    assert [i.name for i in r.items] == ["clean.nam", "lead.nam", "crunch.nam", "extra.nam"]
    assert len(r.sets) == 1 and r.sets[0].gear == "Friedman BE-100"
    assert [i.name for i in r.singles] == ["extra.nam"]
    assert "readme" not in " ".join(i.name for i in r.items)


def test_intake_unreadable_file_is_one_line_and_the_rest_still_arrive():
    r = nam_intake.intake([("bad.nam", b"{not json"), ("ok.nam", _nam("ok"))])
    assert r.items[0].record is None and r.items[0].error
    assert r.items[1].record is not None
    assert "1 not readable: bad.nam:" in r.line


# --- duplicates --------------------------------------------------------------

def test_duplicate_detection_by_sha256_within_the_input_and_against_the_library():
    data = _nam("BE lead")
    twice = nam_intake.intake([("a.nam", data), ("copy of a.nam", data)])
    assert len(twice.items) == 1
    assert twice.duplicates == [{"name": "copy of a.nam",
                                 "sha256": hashlib.sha256(data).hexdigest(),
                                 "same_as": "a.nam"}]
    assert "1 already in your library, skipped" in twice.line
    known = {hashlib.sha256(data).hexdigest()}
    again = nam_intake.intake([("a.nam", data)], known=known)
    assert again.items == [] and again.duplicates[0]["same_as"] == "your library"
    assert again.line == "1 already in your library, skipped"


# --- sets and mapping --------------------------------------------------------

def test_mapping_four_or_fewer_of_one_amp_go_to_channels_in_gain_order():
    r = nam_intake.intake([
        ("lead.nam", _nam("BE lead", tone="hi_gain")),
        ("clean.nam", _nam("BE clean", tone="clean")),
        ("crunch.nam", _nam("BE crunch", tone="crunch")),
    ])
    assert len(r.sets) == 1
    m = r.sets[0].mapping
    assert [(x["name"], x["channel"]) for x in m] == \
        [("clean.nam", "A"), ("crunch.nam", "B"), ("lead.nam", "C")]
    assert all(x["to"] == "channel" for x in m)
    assert r.sets[0].line == "3 captures of one amp (Friedman BE-100), mapped to channels A to C"
    assert r.line.startswith("3 captures of one amp")


def test_mapping_more_than_four_go_to_scenes():
    files = [(f"{t}{i}.nam", _nam(f"BE {t} {i}", tone=t))
             for i, t in enumerate(["clean", "crunch", "hi_gain", "hi_gain", "clean"])]
    r = nam_intake.intake(files)
    m = r.sets[0].mapping
    assert [x["to"] for x in m] == ["scene"] * 5
    assert [x["scene"] for x in m] == [1, 2, 3, 4, 5]
    # gain order: both cleans, then the crunch, then the two hi-gains
    assert [x["name"] for x in m] == ["clean0.nam", "clean4.nam", "crunch1.nam",
                                      "hi_gain2.nam", "hi_gain3.nam"]
    assert r.sets[0].line.endswith("mapped to scenes 1 to 5")


def test_mapping_keeps_file_order_when_tone_type_is_not_on_file():
    r = nam_intake.intake([
        ("z.nam", _nam("BE z", tone=None)),
        ("a.nam", _nam("BE a", tone="clean")),
    ])
    assert [x["name"] for x in r.sets[0].mapping] == ["z.nam", "a.nam"]


def test_mapping_mixed_amps_stay_separate_and_lone_ones_are_singles():
    r = nam_intake.intake([
        ("f1.nam", _nam("F1", make="Friedman", model="BE-100", tone="clean")),
        ("f2.nam", _nam("F2", make="Friedman", model="BE-100", tone="hi_gain")),
        ("m1.nam", _nam("M1", make="Mesa", model="Mark IV")),
        ("n1.nam", _bare("n1")),
    ])
    assert [s.gear for s in r.sets] == ["Friedman BE-100"]
    assert sorted(i.name for i in r.singles) == ["m1.nam", "n1.nam"]
    assert "2 on their own, added to your library" in r.line


# --- the route and the page ----------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


def test_route_answers_records_sets_duplicates_and_the_line(client):
    files = [{"name": n, "data": base64.b64encode(b).decode()} for n, b in [
        ("clean.nam", _nam("BE clean", tone="clean")),
        ("lead.nam", _nam("BE lead", tone="hi_gain")),
        ("lead again.nam", _nam("BE lead", tone="hi_gain")),
    ]]
    r = client.post("/api/captures/intake", json={"files": files})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["items"]) == 2 and len(d["duplicates"]) == 1
    assert d["sets"][0]["count"] == 2
    assert [m["channel"] for m in d["sets"][0]["mapping"]] == ["A", "B"]
    assert d["line"].startswith("2 captures of one amp (Friedman BE-100), mapped to channels A to B")
    assert d["items"][0]["record"]["needs_cab"] is True
    r = client.post("/api/captures/intake", json={"files": []})
    assert r.status_code == 400
    r = client.post("/api/captures/intake", json={"files": [{"name": "x.nam", "data": "%%%"}]})
    assert r.status_code == 400


def test_route_touches_nothing_on_the_unit(client, monkeypatch):
    sent = []
    sim = server._fm9
    real = sim.outp.send
    monkeypatch.setattr(sim.outp, "send", lambda m: (sent.append(m), real(m)))
    client.post("/api/captures/intake", json={"files": [
        {"name": "a.nam", "data": base64.b64encode(_nam("a")).decode()}]})
    assert sent == []


def test_ui_has_the_drop_target_and_shows_the_line():
    assert "function namDropSetup()" in UI and "namDropSetup();" in UI
    # #227: the drop takes a picture first; everything else still goes to
    # the capture intake exactly as before
    drop = UI[UI.index("zone.addEventListener('drop', e => {"):]
    drop = drop[:drop.index("\n  });")]
    assert "if (pic) { setPicture(pic); return; }" in drop and "runNamIntake(files);" in drop
    assert "fetch('/api/captures/intake'" in UI
    assert "chatNote(d.line);" in UI
    assert "Drop pictures or .nam here." in UI
    assert ".composer.dropping" in UI
    # installing is not offered here: no install call in the intake path
    body = UI[UI.index("async function runNamIntake"):UI.index("function growPrompt()")]
    assert "/api/install" not in body and "capture" in body
