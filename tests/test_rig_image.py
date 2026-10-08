"""#227: a picture of a rig, read by a confined reader into the same rig
graph a text source gives, through the same routes, never touching a device."""
import base64
import json
import os
import sys
from pathlib import Path

sys.argv = ["x"]
import pytest
from fastapi.testclient import TestClient

import server
from fm9 import describe, planner

ROOT = Path(__file__).resolve().parent.parent
PAGE = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
DIAGRAM = (ROOT / "tests" / "fixtures" / "rig_diagram_synthetic.png").read_bytes()
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32

SPEC = {"found": True, "summary": "wah and a TS808 into a JCM800 and a Twin in parallel",
        "scenes": [], "stated": [], "vague": [], "quotes": [],
        "rig": {"schema_version": 1,
                "nodes": [{"id": "ts", "role": "drive", "label": "TS808", "provenance": "observed"},
                          {"id": "jcm", "role": "amp", "label": "JCM800", "provenance": "observed"},
                          {"id": "twin", "role": "amp", "label": "Fender Twin", "provenance": "observed"},
                          {"id": "midi", "role": "controller", "label": "MIDI controller", "provenance": "observed"}],
                "edges": [{"from": "ts", "to": "jcm", "kind": "audio", "provenance": "observed"},
                          {"from": "ts", "to": "twin", "kind": "audio", "provenance": "observed"},
                          {"from": "midi", "to": "twin", "kind": "control", "provenance": "observed"}],
                "unknowns": []}}


class FakeReader:
    """Records how the reader was called and what was in its folder."""

    def __init__(self, answer=SPEC, raise_exc=None):
        self.answer, self.raise_exc, self.calls = answer, raise_exc, []

    def __call__(self, prompt, cancel=None, cwd=None, image=None):
        files = sorted(os.listdir(cwd)) if cwd else []
        self.calls.append({"prompt": prompt, "cwd": cwd, "image": image, "files": files,
                           "mode": oct(os.stat(cwd).st_mode & 0o777) if cwd else None})
        if self.raise_exc:
            raise self.raise_exc
        return json.dumps(self.answer)


# -- REQ-001: kinds by bytes, refusals, the spec, the private folder ----------------

@pytest.mark.parametrize("data, kind", [(DIAGRAM, "png"), (JPEG, "jpeg"), (WEBP, "webp")])
def test_image_kind_comes_from_the_bytes(data, kind):
    assert describe.image_kind(data) == kind


@pytest.mark.parametrize("data, words", [
    (b"", "is empty"),
    (b"GIF89a" + b"\x00" * 20, "not a PNG, JPEG or WebP"),
    (b"%PDF-1.7" + b"\x00" * 20, "not a PNG, JPEG or WebP"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * (describe.MAX_IMAGE + 1), "pictures up to 10 MB"),
])
def test_image_refusals_are_in_words(data, words):
    with pytest.raises(describe.SourceError, match=words):
        describe.check_image(data)


def test_image_extract_gives_the_same_spec_and_graph(monkeypatch):
    reader = FakeReader()
    monkeypatch.setattr(describe, "_ask", reader)
    spec = describe.extract_image(DIAGRAM, note="my 2026 rig")
    assert spec["rig"]["nodes"][1]["label"] == "JCM800" and "rig_problems" not in spec
    from fm9 import riggraph
    assert sorted(p["nodes"][-1] for p in riggraph.audio_paths(spec["rig"])["paths"]) == ["jcm", "twin"]
    call = reader.calls[0]
    assert call["image"] == "rig.png" and call["files"] == ["rig.png"]
    assert call["prompt"].startswith(describe.IMAGE_PREAMBLE)
    assert "never instructions" in call["prompt"]
    assert "the picture ./rig.png" in call["prompt"] and "'my 2026 rig'" in call["prompt"]


def test_temp_folder_is_private_and_removed_after_success(monkeypatch):
    reader = FakeReader()
    monkeypatch.setattr(describe, "_ask", reader)
    describe.extract_image(JPEG)
    call = reader.calls[0]
    assert call["mode"] == "0o700" and call["files"] == ["rig.jpg"]
    assert not os.path.exists(call["cwd"])


@pytest.mark.parametrize("exc", [describe.SourceError("the reader failed"),
                                 describe.SourceCancelled("stopped")])
def test_temp_folder_is_removed_after_an_error_or_stop(monkeypatch, exc):
    reader = FakeReader(raise_exc=exc)
    monkeypatch.setattr(describe, "_ask", reader)
    with pytest.raises(type(exc)):
        describe.extract_image(DIAGRAM)
    assert not os.path.exists(reader.calls[0]["cwd"])


# -- REQ-002: the reader is confined, text is unchanged ----------------------------------

class Proc:
    def __init__(self, argv, **kw):
        Proc.seen = {"argv": argv, "cwd": kw.get("cwd")}
        self.args = argv
        self.returncode = 0

    def communicate(self, timeout=None):
        return json.dumps({"result": json.dumps(SPEC)}), ""


def test_confine_flags_on_the_picture_command_line(monkeypatch):
    monkeypatch.setattr(planner, "find_claude_cli", lambda: "/bin/claude")
    monkeypatch.setattr(describe.subprocess, "Popen", Proc)
    describe.extract_image(DIAGRAM)
    argv = Proc.seen["argv"]
    tail = argv[argv.index("--model") + 2:]
    assert tail == ["--restricted", "--tools", "Read", "--strict-mcp-config",
                    "--allowedTools", "Read(./rig.png)"]
    assert Proc.seen["cwd"].startswith(os.path.join(__import__("tempfile").gettempdir(), "tonecommand-picture-"))


def test_confine_flags_never_touch_the_text_command_line(monkeypatch):
    monkeypatch.setattr(planner, "find_claude_cli", lambda: "/bin/claude")
    monkeypatch.setattr(describe.subprocess, "Popen", Proc)
    describe.extract("a long enough description of a wah into a TS808 into a JCM800")
    argv = Proc.seen["argv"]
    assert argv[0] == "/bin/claude" and argv[1] == "-p"
    assert argv[3:] == ["--output-format", "json", "--model", planner.cli_model()]
    assert "--restricted" not in argv and "--allowedTools" not in argv
    assert Proc.seen["cwd"] == __import__("tempfile").gettempdir()


def test_confine_no_cli_means_a_plain_refusal_for_a_picture(monkeypatch):
    monkeypatch.setattr(planner, "find_claude_cli", lambda: None)
    with pytest.raises(describe.SourceError, match="Reading a picture needs the Claude CLI on this computer"):
        describe.extract_image(DIAGRAM)


# -- REQ-003: routes, links, readiness --------------------------------------------------

class Tripwire:
    def __getattr__(self, name):
        raise AssertionError(f"the picture route touched the device: {name}")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", Tripwire())
    monkeypatch.setattr(server, "get_fm9", lambda: Tripwire())
    return TestClient(server.app)


@pytest.mark.parametrize("encode", [lambda b: base64.b64encode(b).decode(),
                                    lambda b: "data:image/png;base64," + base64.b64encode(b).decode()],
                         ids=["base64", "data-url"])
def test_route_reads_a_picture_with_the_note(client, monkeypatch, encode):
    reader = FakeReader()
    monkeypatch.setattr(describe, "_ask", reader)
    r = client.post("/api/describe/read", json={"source": "my rig", "image": encode(DIAGRAM)})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source"]["kind"] == "image" and d["rig_explain"]
    assert "'my rig'" in reader.calls[0]["prompt"]


def test_route_stream_reads_a_picture(client, monkeypatch):
    monkeypatch.setattr(describe, "_ask", FakeReader())
    r = client.post("/api/describe/read/stream",
                    json={"source": "", "image": base64.b64encode(DIAGRAM).decode()})
    assert "event: spec" in r.text and '"kind": "image"' in r.text
    assert "reading the picture" in r.text


@pytest.mark.parametrize("image, words", [("not base64 !!!", "could not be read as an image"),
                                          (base64.b64encode(b"GIF89a....").decode(), "not a PNG, JPEG or WebP")])
def test_route_refuses_a_bad_picture_in_words(client, image, words):
    r = client.post("/api/describe/read", json={"source": "", "image": image})
    assert r.status_code == 400 and words in r.json()["error"]


def test_link_to_a_picture_is_fetched_and_read(client, monkeypatch):
    fetched = []
    monkeypatch.setattr(describe, "fetch_image", lambda url: fetched.append(url) or DIAGRAM)
    monkeypatch.setattr(describe, "_ask", FakeReader())
    url = "https://example.com/rigs/board.PNG?width=900"
    d = client.post("/api/describe/read", json={"source": url}).json()
    assert fetched == [url] and d["source"] == {"kind": "image", "url": url, "title": "", "notes": []}


@pytest.mark.parametrize("text, is_link", [("https://x.com/a.jpg", True), ("https://x.com/a.webp?x=1", True),
                                           ("https://youtu.be/abc", False), ("https://x.com/a.png page", False),
                                           ("a.png", False)])
def test_link_detection_is_by_extension_only(text, is_link):
    assert describe.looks_like_image_link(text) is is_link


def test_ready_reports_whether_pictures_can_be_read(client, monkeypatch):
    monkeypatch.setattr(planner, "find_claude_cli", lambda: "/bin/claude")
    assert client.get("/api/describe/ready").json()["images"] is True
    monkeypatch.setattr(planner, "find_claude_cli", lambda: None)
    assert client.get("/api/describe/ready").json()["images"] is False


# -- REQ-004: the page ---------------------------------------------------------------------

def test_page_takes_a_picture_by_paste_drop_and_attach():
    assert '<button id="attachpic" class="attach"' in PAGE
    assert '<input type="file" id="picfile" accept="image/png,image/jpeg,image/webp" hidden>' in PAGE
    assert "$('prompt').addEventListener('paste', e => {" in PAGE
    assert "const pic = files.find(f => PIC_TYPES.includes(f.type));" in PAGE
    assert "runNamIntake(files);" in PAGE                         # .nam drops unchanged
    assert "analyzeSource(said, pic);" in PAGE
    assert "body: JSON.stringify(pic ? {source: raw, image: pic.data} : {source: raw})});" in PAGE
    assert "if (d.images === false) picsReadable = false;" in PAGE
    assert '<button id="picremove" title="remove the picture">REMOVE</button>' in PAGE


def test_page_card_scrolls_only_its_pane_never_the_app_frame():
    """1.5.10 scrolled #shell, the fixed app frame, with scrollIntoView: the
    header left the screen and the footer slid over the rig card. Measured in
    a browser at 1490x698 (shell scrollTop 408 before, 0 after)."""
    ask = PAGE.split("function askAboutBuild(spec, note)")[1].split("\n}\n")[0]
    assert ".scrollIntoView(" not in ask                         # a call, not the comment naming it
    assert "pane.scrollTop += ask.getBoundingClientRect().top - pane.getBoundingClientRect().top;" in ask
    # the pane is a scroll box while the question is open, and the finished
    # progress panel steps aside instead of being drawn over
    assert "#pane-request:has(> #srcask:not([hidden])) { overflow-y: auto; min-height: 0; }" in PAGE
    assert "$('srcprogress').hidden = true;" in ask
