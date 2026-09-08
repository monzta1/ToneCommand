"""Making `measured` reachable, and keeping it honest.

The anchor state has existed, been tested, and been unreachable by any route
the product offers: every install path writes a bare display name, so no slot
could become a measured anchor by USING ToneCommand. It could only be forged
by hand-editing user_cabs.json, which is the wrong way round entirely.

This is the missing step. It is deliberately something the player does rather
than something inferred from a name, because inferring identity from a name
is the ranking-as-identity mistake that put a Soldano capture behind an
unrelated slot (brief 26.1).
"""
import json

import pytest

import sys

sys.argv = ["x"]
import server
from fm9 import ir_service, user_cabs


@pytest.fixture
def cabs_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_USER_CABS", str(tmp_path / "user_cabs.json"))
    monkeypatch.setattr(user_cabs, "_cache", {}, raising=False)
    monkeypatch.setattr(user_cabs, "_stamp", None, raising=False)
    return tmp_path / "user_cabs.json"


@pytest.fixture
def ir(monkeypatch):
    """IRCommand answering about one known, analysed file."""
    answers = {}

    def check(path):
        return answers.get(str(path), {"in_library": False,
                                       "has_curve": False, "measured": False})

    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "measured_check", check)
    return answers


def _link(body):
    out = server.api_user_cabs_link(body)
    if hasattr(out, "status_code"):
        return out.status_code, json.loads(bytes(out.body))
    return 200, out


def test_a_linked_slot_becomes_a_measured_anchor(cabs_file, ir, tmp_path):
    """The whole point: the state is reachable by using the product."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF0123456789")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True,
                    "brightness": 2400.0}
    code, out = _link({"ordinal": 26, "source": str(src), "name": "Mine"})
    assert code == 200 and out["linked"] is True

    rec = user_cabs.record(server.USER_CAB_BANK, 26)
    assert rec["source"] == str(src)
    assert rec["digest"] == ir_service.digest_of(src)

    anchor = server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26,
                     "name": "Mine"}})
    assert anchor["state"] == "measured"
    assert anchor["reference"] == str(src)


def test_the_link_is_refused_for_a_file_the_library_does_not_hold(cabs_file,
                                                                  ir, tmp_path):
    """A link to something unmeasured is a slot that claims an anchor and
    produces no comparison, which is worse than no link."""
    src = tmp_path / "elsewhere.wav"
    src.write_bytes(b"RIFF")
    code, out = _link({"ordinal": 26, "source": str(src)})
    assert code == 400 and "not in your IR library" in out["error"]
    assert user_cabs.record(server.USER_CAB_BANK, 26) is None


def test_an_unanalysed_library_file_says_what_to_do(cabs_file, ir, tmp_path):
    src = tmp_path / "known.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": False, "measured": False}
    code, out = _link({"ordinal": 26, "source": str(src)})
    # Parenthesised. Written as `code == 409 and A or B` this parses as
    # `(code == 409 and A) or B`, so the status-code half could be dropped
    # entirely and the test still passed on the message alone.
    assert code == 409
    assert ("analyse" in out["error"]) or ("analyze" in out["error"])


def test_a_silent_ircommand_is_refused_not_assumed(cabs_file, monkeypatch,
                                                   tmp_path):
    """The check that gates a numeric claim must read {} as NO."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    monkeypatch.setattr(ir_service, "enabled", lambda: True)
    monkeypatch.setattr(ir_service, "measured_check", lambda p: {})
    code, out = _link({"ordinal": 26, "source": str(src)})
    assert code == 503
    assert user_cabs.record(server.USER_CAB_BANK, 26) is None


def test_a_missing_file_is_refused(cabs_file, ir):
    code, out = _link({"ordinal": 26, "source": "/nope/gone.wav"})
    assert code == 400 and "no file at" in out["error"]


def test_only_the_user_bank_can_be_linked(cabs_file, ir, tmp_path):
    """Brief 26.1: a factory slot's identity is the manufacturer's own label,
    and a hand-written link overriding it is the boundary error."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    code, out = _link({"bank": 3, "ordinal": 42, "source": str(src)})
    assert code == 400 and "factory" in out["error"]


def test_renaming_a_linked_slot_does_not_discard_the_link(cabs_file, ir,
                                                          tmp_path):
    """set_name used to overwrite the whole entry with a bare string, so
    typing a nicer name silently stopped the slot being an anchor."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "First"})
    user_cabs.set_name(server.USER_CAB_BANK, 26, "A better name")
    rec = user_cabs.record(server.USER_CAB_BANK, 26)
    assert isinstance(rec, dict), "renaming threw the provenance away"
    assert rec["source"] == str(src)
    assert rec["label"] == "A better name"
    assert user_cabs.name(server.USER_CAB_BANK, 26) == "A better name"


def test_clearing_the_name_still_clears_the_slot(cabs_file, ir, tmp_path):
    """Keeping the link on RENAME must not make a slot impossible to clear."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "First"})
    user_cabs.set_name(server.USER_CAB_BANK, 26, "")
    assert user_cabs.record(server.USER_CAB_BANK, 26) is None


def test_unlinking_leaves_the_name_behind(cabs_file, ir, tmp_path):
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "Mine"})
    code, out = _link({"ordinal": 26, "source": ""})
    assert code == 200 and out["linked"] is False
    assert user_cabs.name(server.USER_CAB_BANK, 26) == "Mine"
    assert server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26}})[
            "state"] != "measured"


def test_a_file_changed_after_linking_stops_anchoring(cabs_file, ir, tmp_path):
    """The digest is what makes the link mean anything later. A re-export
    keeps the path and changes the sound."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF0123456789")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "Mine"})
    assert server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26}})[
            "state"] == "measured"
    src.write_bytes(b"RIFFsomethingelse")
    assert server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26}})[
            "state"] != "measured"


def test_the_answer_does_not_overstate_what_a_link_proves(cabs_file, ir,
                                                          tmp_path):
    """A digest proves the named disk file has not changed. Nothing can read
    the IR back off the FM9, so the device side is the player's word, and the
    reply has to say so rather than reporting a verified slot."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _, out = _link({"ordinal": 26, "source": str(src)})
    assert "cannot read the IR back off the FM9" in out["detail"] \
        or "read the IR back off the FM9" in out["detail"]
    assert "verified" not in out["detail"]


# --- an install is not a rename (2026-09-08) ------------------------------
#
# Found by the fourth review, and created by the fix before it. set_name was
# taught to MERGE so a rename would not discard a link, and the install path
# is a set_name call. So writing a different IR into a linked slot kept the
# old source and digest: the file on disk was untouched, the digest still
# matched, IRCommand still held its curve, and the slot went on serving as a
# measured anchor for a capture it no longer contained. Every "x dB from
# current" after that was measured against something the player cannot hear.

def test_installing_into_a_linked_slot_drops_the_link(cabs_file, ir, tmp_path):
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF0123456789")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "OwnHammer Brit V30"})
    assert server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26}})[
            "state"] == "measured"

    # Exactly what /api/install-cab does after a verified write.
    user_cabs.relabel_installed(server.USER_CAB_BANK, 26, "A Different IR")

    rec = user_cabs.record(server.USER_CAB_BANK, 26)
    assert not isinstance(rec, dict), \
        "the slot holds different audio and kept the old file's provenance"
    assert user_cabs.name(server.USER_CAB_BANK, 26) == "A Different IR"
    assert server.current_anchor(
        {"cab_sel": {"bank": server.USER_CAB_BANK, "ordinal": 26}})[
            "state"] != "measured"


def test_the_install_path_does_not_go_through_set_name(cabs_file):
    """The two writes mean different things and must not share a function:
    one protects a link, the other has to drop it."""
    # The CALLS, not the text. The function's own comment explains why it
    # does not use set_name, and a substring check reads that as a call.
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(server.api_install_cab).lstrip())
    called = {n.func.attr for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert "relabel_installed" in called
    assert "set_name" not in called, \
        "an install through set_name keeps provenance it has just invalidated"


def test_a_rename_still_keeps_the_link(cabs_file, ir, tmp_path):
    """The behaviour the merge was introduced for, so the fix above cannot
    quietly undo it."""
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    _link({"ordinal": 26, "source": str(src), "name": "First"})
    user_cabs.set_name(server.USER_CAB_BANK, 26, "A better name")
    rec = user_cabs.record(server.USER_CAB_BANK, 26)
    assert isinstance(rec, dict) and rec["source"] == str(src)


def test_an_unreadable_recorded_digest_is_a_refusal(cabs_file, ir, tmp_path,
                                                    monkeypatch):
    """digest_of returns "" when a file cannot be read, so a record with no
    digest pointing at an unreadable file compared "" to "" and passed."""
    from fm9 import ir_service
    src = tmp_path / "cap.wav"
    src.write_bytes(b"RIFF")
    ir[str(src)] = {"in_library": True, "has_curve": True, "measured": True}
    monkeypatch.setattr(user_cabs, "record",
                        lambda b, o: {"label": "x", "source": str(src),
                                      "digest": ""})
    monkeypatch.setattr(ir_service, "digest_of", lambda p: "")
    assert ir_service.linked_source(server.USER_CAB_BANK, 26) is None
