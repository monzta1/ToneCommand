"""#186: secret files are owner-only on every OS, and a secret is never
written into a file that is not already private."""
import os
import subprocess
import sys

import pytest

from fm9 import owner_only

WINDOWS = sys.platform == "win32"

# What `icacls <path> /q` prints, as Windows Server 2022 formats it.
SAMPLE = (
    "C:\\Users\\runner\\x\\ai_settings.json NT AUTHORITY\\SYSTEM:(I)(F)\n"
    "                                    BUILTIN\\Administrators:(I)(F)\n"
    "                                    fv-az123\\runneradmin:(I)(F)\n"
    "\n"
    "Successfully processed 1 files; Failed processing 0 files\n"
)


def test_icacls_output_is_read_as_a_list_of_accounts():
    assert owner_only.parse_grantees(SAMPLE, "C:\\Users\\runner\\x\\ai_settings.json") == [
        "NT AUTHORITY\\SYSTEM", "BUILTIN\\Administrators", "fv-az123\\runneradmin"]
    assert owner_only.parse_grantees(
        "c:\\a b\\t.json fv\\me:(F)\n", "C:\\a b\\t.json") == ["fv\\me"]   # spaces, case


def test_the_current_user_is_recognised_by_sid_name_or_machine_name():
    sid = "S-1-5-21-1-2-3-1001"
    assert owner_only.is_me("*S-1-5-21-1-2-3-1001", sid, "me")
    assert owner_only.is_me("FV-AZ123\\Me", sid, "me")
    assert owner_only.is_me("me", sid, "me")
    assert not owner_only.is_me("Everyone", sid, "me")
    assert not owner_only.is_me("BUILTIN\\Administrators", sid, "me")
    assert not owner_only.is_me("fv\\someone-me", sid, "me")


def test_a_failed_lockdown_never_writes_the_secret(tmp_path, monkeypatch):
    """The secret is written only after the file is shown private: when the
    lockdown fails, the write is never reached and nothing is left behind."""
    target = tmp_path / "secret.json"

    def refuse(path):
        raise owner_only.NotPrivate("icacls failed: access denied")
    written = []
    real_write = os.write
    monkeypatch.setattr(owner_only, "tighten", refuse)
    monkeypatch.setattr(owner_only.os, "write", lambda fd, b: written.append(b) or real_write(fd, b))
    with pytest.raises(owner_only.NotPrivate):
        owner_only.write_private(target, "sk-secret")
    assert written == [], "secret bytes were written before the file was private"
    assert list(tmp_path.iterdir()) == []


def test_two_saves_at_once_never_leave_the_secret_readable(tmp_path, monkeypatch):
    """Review finding: both saves shared one temp name, so the second could
    move it away between the first's privacy check and its write, and the
    first then recreated the path with the default mode. Here save B runs
    in full inside save A's privacy check."""
    target = tmp_path / "secret.json"
    real_is_private = owner_only.is_private
    state = {"nested": False}

    def check(p):
        if not state["nested"]:
            state["nested"] = True
            owner_only.write_private(target, "from-B")
        return real_is_private(p)
    monkeypatch.setattr(owner_only, "is_private", check)
    owner_only.write_private(target, "from-A")
    assert target.read_text(encoding="utf-8") == "from-A"
    assert real_is_private(target)
    assert [p.name for p in tmp_path.iterdir()] == ["secret.json"]


def test_a_file_that_will_not_read_as_private_is_refused_and_removed(tmp_path, monkeypatch):
    target = tmp_path / "secret.json"
    monkeypatch.setattr(owner_only, "is_private", lambda p: False)
    with pytest.raises(owner_only.NotPrivate):
        owner_only.write_private(target, "sk-secret")
    assert list(tmp_path.iterdir()) == []


def test_write_private_produces_a_private_file_with_the_text(tmp_path):
    target = tmp_path / "secret.json"
    owner_only.write_private(target, "sk-secret")
    assert target.read_text(encoding="utf-8") == "sk-secret"
    assert owner_only.is_private(target)
    assert [p.name for p in tmp_path.iterdir()] == ["secret.json"]


@pytest.mark.skipif(WINDOWS, reason="POSIX modes; the Windows ACL has its own test")
def test_posix_a_readable_file_is_tightened_to_0600(tmp_path):
    target = tmp_path / "secret.json"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, 0o644)
    assert not owner_only.is_private(target)
    owner_only.write_private(target, "new")
    assert (target.stat().st_mode & 0o777) == 0o600


@pytest.mark.skipif(not WINDOWS, reason="the ACL path exists only on Windows")
def test_windows_an_explicit_everyone_grant_is_removed_and_rejected(tmp_path):
    target = tmp_path / "secret.json"
    target.write_text("old", encoding="utf-8")
    owner_only.tighten(target)
    assert owner_only.is_private(target)
    subprocess.run(["icacls", str(target), "/grant", "*S-1-1-0:R"], check=True, capture_output=True)
    assert not owner_only.is_private(target), "an Everyone grant must not read as private"
    owner_only.write_private(target, "new")
    assert owner_only.is_private(target)
    assert owner_only.grantees(target) and len(owner_only.grantees(target)) == 1
