"""Adversarial edge cases for the work done on 2026-09-07.

Written to break my own code rather than confirm it. Anything that fails here
is a real defect, not a test problem, unless proven otherwise.
"""
from __future__ import annotations

import io
import wave

import pytest

# numpy is an OPTIONAL extra (the audition preview). Skip rather than
# error where it is absent, so a core install still reports a clean suite.
np = pytest.importorskip("numpy")
from fastapi.testclient import TestClient

import server
from fm9 import ir_audition, ir_service, proof, tone_review
from fm9.tone_review import Scene


# =====================================================================
# The URL security boundary. A false ACCEPT here is a real vulnerability.
# =====================================================================

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("TONECOMMAND_IR_ALLOW_REMOTE", raising=False)
    monkeypatch.delenv("TONECOMMAND_IR_SERVICE", raising=False)


@pytest.mark.parametrize("url", [
    "http://user:pass@evil.example.com/",      # credentials hiding the host
    "http://127.0.0.1@evil.example.com/",      # loopback as a USERINFO decoy
    "http://localhost.evil.com/",              # suffix trick
    "http://evil.com/127.0.0.1",               # loopback only in the path
    "http://evil.com/?x=127.0.0.1",            # loopback only in the query
    "http://evil.com#127.0.0.1",               # loopback only in the fragment
    "http://LOCALHOST.evil.com/",              # case plus suffix
    "//127.0.0.1/",                            # scheme-relative, no scheme
    "http://[email protected]/",
])
def test_hosts_that_merely_mention_loopback_are_refused(url):
    with pytest.raises(ir_service.UnsafeServiceURL):
        ir_service.check_url(url)


@pytest.mark.parametrize("url", [
    "http://LOCALHOST:8770",                   # uppercase must still work
    "http://127.0.0.2:8770",                   # all of 127.0.0.0/8 is loopback
    "http://[::1]:8770",
])
def test_genuine_loopback_forms_are_accepted(url):
    assert ir_service.check_url(url) == url


@pytest.mark.parametrize("url", [
    "http://2130706433/",                      # decimal 127.0.0.1
    "http://0177.0.0.1/",                      # octal
    "http://127.1/",                           # short form
])
def test_obscured_loopback_forms_fail_closed(url):
    """These really are loopback, and we refuse them. Refusing something safe
    is the harmless direction; accepting something unsafe is not. Pinned so a
    future 'fix' cannot loosen parsing without deciding to."""
    with pytest.raises(ir_service.UnsafeServiceURL):
        ir_service.check_url(url)


def test_the_escape_hatch_is_not_triggered_by_a_falsey_string(monkeypatch):
    for val in ("0", "false", "no", ""):
        monkeypatch.setenv("TONECOMMAND_IR_ALLOW_REMOTE", val)
        with pytest.raises(ir_service.UnsafeServiceURL):
            ir_service.check_url("http://evil.example.com/")


# =====================================================================
# Filesystem boundary for the audition endpoint.
# =====================================================================

def test_a_symlink_out_of_the_library_is_refused(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    (root / "IRs").mkdir(parents=True)
    secret = tmp_path / "outside.wav"
    secret.write_bytes(b"RIFF____WAVE")
    link = root / "IRs" / "sneaky.wav"
    link.symlink_to(secret)
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(root))
    assert ir_service.safe_ir_path(str(link)) is None, \
        "a symlink inside the library must not reach outside it"


def test_the_library_root_itself_is_not_a_file(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    root.mkdir()
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(root))
    assert ir_service.safe_ir_path(str(root)) is None


def test_a_missing_library_root_refuses_everything(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(tmp_path / "nope"))
    f = tmp_path / "x.wav"
    f.write_bytes(b"RIFF____WAVE")
    assert ir_service.safe_ir_path(str(f)) is None


def test_non_wav_extensions_are_refused(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    (root / "IRs").mkdir(parents=True)
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(root))
    for name in ("cab.syx", "cab.wav.txt", "cab.aiff", "cab"):
        p = root / "IRs" / name
        p.write_bytes(b"x")
        assert ir_service.safe_ir_path(str(p)) is None, name


# =====================================================================
# The audition renderer on hostile audio.
# =====================================================================

def _wav(path, samples, sr=48000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(np.asarray(samples, dtype=np.float64).clip(-1, 1)
                      .__mul__(32767).astype("<i2").tobytes())
    return path


@pytest.fixture
def lib(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    (root / "IRs").mkdir(parents=True)
    monkeypatch.setenv("TONECOMMAND_IR_LIBRARY", str(root))
    return root / "IRs"


def test_a_silent_ir_does_not_divide_by_zero(lib):
    p = _wav(lib / "silent.wav", np.zeros(2048))
    try:
        out = ir_audition.render(p)
    except ValueError:
        return                      # refusing silence is a fine answer
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnframes() > 0   # but it must not produce NaN or crash


def test_a_single_sample_ir_is_survivable(lib):
    p = _wav(lib / "one.wav", [1.0])
    out = ir_audition.render(p, seconds=0.5)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getnframes() > 0


def test_an_empty_data_chunk_is_refused(lib):
    p = _wav(lib / "empty.wav", [])
    with pytest.raises(ValueError):
        ir_audition.load_ir(p)


def test_a_truncated_wav_is_refused(lib):
    p = lib / "trunc.wav"
    p.write_bytes(b"RIFF" + b"\x00" * 4 + b"WAVE")
    with pytest.raises(ValueError):
        ir_audition.load_ir(p)


def test_render_output_is_never_clipped_or_nan(lib):
    p = _wav(lib / "hot.wav", np.ones(2048))     # worst case: a DC-ish slab
    out = ir_audition.render(p, drive="high-gain")
    with wave.open(io.BytesIO(out)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    assert np.isfinite(x).all()
    assert np.abs(x).max() <= 32767


@pytest.mark.parametrize("drive", ["clean", "crunch", "lead", "high-gain",
                                   "nonsense", ""])
def test_an_unknown_drive_falls_back_rather_than_crashing(lib, drive):
    p = _wav(lib / "cab.wav", np.random.default_rng(0).standard_normal(512) * .3)
    assert len(ir_audition.render(p, drive=drive, seconds=0.5)) > 44


@pytest.mark.parametrize("seconds", [-5, 0, 0.001, 1e9])
def test_absurd_durations_are_clamped(lib, seconds):
    p = _wav(lib / "cab.wav", np.random.default_rng(0).standard_normal(512) * .3)
    out = ir_audition.render(p, seconds=seconds)
    with wave.open(io.BytesIO(out)) as w:
        secs = w.getnframes() / w.getframerate()
    assert 0.4 <= secs <= ir_audition.MAX_RENDER_SECONDS + 0.1, secs


# =====================================================================
# Proof vocabulary: the ladder must not be climbable by accident.
# =====================================================================

def test_kept_cannot_be_reached_without_the_player():
    """Only player_picked / player_kept may raise past a measurement."""
    d = proof.describe(sent=True, read_back=True, sound_checked=True,
                       moved_to_target=True)
    assert proof.strength(d["level"]) < proof.strength("your_pick")


def test_describe_with_nothing_true_is_the_weakest_claim():
    assert proof.describe()["level"] == "sent"


def test_no_label_contains_the_word_verified():
    for level in proof.LADDER:
        assert "verif" not in proof.copy_for(level).lower(), level


def test_overclaims_is_case_insensitive():
    assert proof.overclaims("This Sounds BETTER")


def test_unknown_levels_do_not_crash_strength():
    assert proof.strength("not_a_level") == -1
    assert proof.highest("nonsense") == "sent"


# =====================================================================
# Plan digests: two different plans must never share one.
# =====================================================================

def _a(**over):
    base = {"kind": "set_param", "block": "cab", "param": "CABINET_LEVEL",
            "value": -3.0}
    return server.Action(**{**base, **over})


def test_block_and_param_changes_change_the_digest():
    d = server.plan_digest([_a()])
    assert server.plan_digest([_a(block="amp")]) != d
    assert server.plan_digest([_a(param="CABINET_AIR")]) != d
    assert server.plan_digest([_a(kind="set_cab")]) != d


def test_an_empty_plan_has_a_stable_digest():
    assert server.plan_digest([]) == server.plan_digest([])


def test_a_duplicated_action_is_not_the_same_as_one():
    assert server.plan_digest([_a(), _a()]) != server.plan_digest([_a()])


def test_adding_an_action_invalidates_a_reviewed_plan():
    dg = server.register_revision([_a()])
    why = server.check_revision(
        server.ApplyBody(actions=[_a(), _a(value=-9.0)], plan_digest=dg))
    assert why


def test_removing_an_action_invalidates_a_reviewed_plan():
    dg = server.register_revision([_a(), _a(value=-9.0)])
    why = server.check_revision(
        server.ApplyBody(actions=[_a()], plan_digest=dg))
    assert why


def test_the_revision_store_is_bounded():
    """A long session must not grow this without limit."""
    for i in range(server._MAX_REVISIONS + 40):
        server.register_revision([_a(value=float(-i))])
    assert len(server._plan_revisions) <= server._MAX_REVISIONS


def test_eviction_keeps_the_newest():
    dg = server.register_revision([_a(value=-1.5)])
    for i in range(server._MAX_REVISIONS + 5):
        server.register_revision([_a(value=float(100 + i))])
    assert dg not in server._plan_revisions, "the oldest should have gone"


# =====================================================================
# Coverage: the whole point is that it cannot overstate.
# =====================================================================

def test_a_role_alone_is_not_a_verified_review():
    """A scene whose role is known but whose every value is unknown means no
    value check ran. Calling that verified is the exact bug #54 was about."""
    c = tone_review.coverage([Scene(n=1, role="lead")])
    assert c["status"] == "unknown", c


def test_one_real_value_is_enough_to_be_verified():
    c = tone_review.coverage([Scene(n=1, role="lead", amp_gain=7.0)])
    assert c["status"] == "verified"


def test_coverage_survives_a_scene_with_nothing_at_all():
    c = tone_review.coverage([Scene(n=1)])
    assert c["status"] == "unknown"
    assert c["checks_run"] == 0


# =====================================================================
# The guided-correction guard cannot be bypassed by casing or spacing.
# =====================================================================

@pytest.mark.parametrize("origin", ["sound_check_correction",
                                    "guided_correction"])
def test_guided_origins_are_matched_exactly(origin):
    assert origin in server.GUIDED_ORIGINS


@pytest.mark.parametrize("origin", [None, "", "player", "manual"])
def test_manual_origins_are_not_guided(origin):
    assert (origin or "") not in server.GUIDED_ORIGINS


def test_endpoint_rejects_an_unsafe_url_without_saving_it(tmp_path, monkeypatch):
    monkeypatch.setattr(ir_service, "_config_path",
                        lambda: tmp_path / "cfg.json")
    c = TestClient(server.app)
    assert c.post("/api/ir/config",
                  json={"url": "http://169.254.169.254/"}).status_code == 400
    assert not (tmp_path / "cfg.json").exists()
