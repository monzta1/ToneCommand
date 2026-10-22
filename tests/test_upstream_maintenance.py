"""Maintenance tools operate on disposable Git repos, never the rig or AI."""
import json
import subprocess
from pathlib import Path

import pytest

from tools import release_audit, upstream_status, bootstrap_fx3_kb


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Offline test")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.5.4"\n', encoding="utf-8")
    (tmp_path / "server.py").write_text("# baseline\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "Synthetic foundation")
    return tmp_path


@pytest.mark.parametrize("path", ["backups/export.json", "kb/index.json", "file.syx",
    "FILE.NAM", "user/model.fasBundle", "ai_settings.json", "store_slots.json",
    "config/cab_models.full.json", ".env", ".env.local", "local\\device_settings.json",
    "devices/learned/private-profile.json", "devices\\learned\\private-profile.json"])
def test_private_artifacts_are_refused(path):
    assert release_audit.inspect_blob(path, b"{}") == ["private-artifact"]


def test_public_metadata_and_synthetic_tests_are_allowed():
    assert release_audit.inspect_blob("config/axefx3_upstream.json", b"{}") == []
    assert release_audit.inspect_blob("devices/profiles/reviewed-profile.json", b"{}") == []
    assert release_audit.inspect_blob("tests/test_account.py", b"token = 'sk-test'") == []


def test_credential_rules_never_need_printing_the_value():
    raw = ("ghp_" + "a" * 36).encode()
    assert release_audit.inspect_blob("source.py", raw) == ["github-token"]
    token = json.dumps({"refresh_token": "a" * 40}).encode()
    assert release_audit.inspect_blob("source.json", token) == ["literal-account-token"]


def test_index_scan_includes_new_private_files_and_ignores_unstaged_changes(repo):
    (repo / "server.py").write_text("ghp_" + "a" * 36, encoding="utf-8")
    assert release_audit.audit(repo, staged=True) == []
    (repo / "ai_settings.json").write_text("{}", encoding="utf-8")
    git(repo, "add", "ai_settings.json")
    assert release_audit.audit(repo, staged=True) == [
        {"path": "ai_settings.json", "rules": ["private-artifact"]}]
    assert release_audit.audit(repo, ref="HEAD") == []


def test_committed_scan_does_not_inherit_owner_settings(repo):
    (repo / "backups").mkdir()
    (repo / "backups/export.syx").write_bytes(b"private")
    git(repo, "add", "backups/export.syx")
    git(repo, "commit", "-qm", "Synthetic private artifact")
    assert release_audit.audit(repo) == [
        {"path": "backups/export.syx", "rules": ["private-artifact"]}]


def manifest(repo, foundation, audited):
    (repo / "config").mkdir(exist_ok=True)
    data = {"upstream_url": "https://github.com/monzta1/ToneCommand.git",
        "upstream_branch": "main", "integration_foundation": foundation,
        "audited_commit": audited, "audited_version": "1.5.14", "integration_status": "pending",
        "rules": [{"name": "shared", "paths": ["server.py"], "policy": "port-and-regression"}]}
    (repo / "config/axefx3_upstream.json").write_text(json.dumps(data), encoding="utf-8")


def test_public_kb_bootstrap_is_private_and_never_replaces_existing_knowledge(repo):
    foundation=git(repo,'rev-parse','HEAD');manifest(repo,foundation,foundation)
    (repo/'.gitignore').write_text('kb/\n',encoding='utf-8')
    (repo/'docs').mkdir()
    for name in ('FW33-COMPATIBILITY.md','AFX3-UPSTREAM-MAINTENANCE.md'):
        (repo/'docs'/name).write_text('Public facts only\n',encoding='utf-8')
    target=bootstrap_fx3_kb.bootstrap(repo)
    index=json.loads((target/'index.json').read_text(encoding='utf-8'))
    for name in index['always_load']+[n for topic in index['topics'] for n in topic['files']]:
        assert (target/name).is_file()
    before=(target/'ALWAYS.md').read_bytes()
    with pytest.raises(ValueError,match='already'):bootstrap_fx3_kb.bootstrap(repo)
    assert (target/'ALWAYS.md').read_bytes()==before
    assert git(repo,'check-ignore','kb/INDEX.md')=='kb/INDEX.md'
    assert not git(repo,'ls-files','--','kb')


def test_kb_bootstrap_refuses_a_publishable_kb(repo):
    with pytest.raises(ValueError,match='gitignored'):bootstrap_fx3_kb.bootstrap(repo)
    assert not (repo/'kb').exists()


def test_status_is_offline_read_only_and_does_not_claim_integration(repo):
    foundation = git(repo, "rev-parse", "HEAD")
    (repo / "server.py").write_text("# new source\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.5.14"\n', encoding="utf-8")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic upstream update")
    target = git(repo, "rev-parse", "HEAD")
    manifest(repo, foundation, foundation)
    (repo / "server.py").write_text("# uncommitted owner work\n", encoding="utf-8")
    before = git(repo, "status", "--porcelain")
    data = upstream_status.report(repo, target=target)
    assert data["target_version"] == "1.5.14"
    assert data["new_since_audit"] and data["new_commit_count"] == 1
    assert data["integration_status"] == "pending"
    assert data['foundation_in_head']
    assert data["tracked_worktree_dirty"]
    assert next(e for e in data["incoming"] if e["path"] == "server.py")["overlaps_local"]
    assert git(repo, "status", "--porcelain") == before
    assert git(repo, "rev-parse", "HEAD") == target


def test_fetch_refuses_an_unexpected_or_credential_bearing_remote(repo, monkeypatch):
    head = git(repo, "rev-parse", "HEAD")
    manifest(repo, head, head)
    git(repo, "remote", "add", "upstream", "https://example.invalid/other.git")
    calls = []
    original = upstream_status.git

    def observe(root, *args):
        calls.append(args)
        return original(root, *args)

    monkeypatch.setattr(upstream_status, "git", observe)
    with pytest.raises(ValueError, match="differs"):
        upstream_status.report(repo, fetch=True, target=head)
    assert not any(call[0] == "fetch" for call in calls)


def test_hardware_rules_take_precedence_over_general_patterns():
    data = json.loads((Path(__file__).parents[1] / "config/axefx3_upstream.json").read_text(encoding="utf-8"))
    assert upstream_status.classify("fm9/device.py", data["rules"])[1] == "manual-hardware-review"
    assert upstream_status.classify("fm9/nam_install.py", data["rules"])[1] == "manual-hardware-review"
    assert upstream_status.classify("fm9/tone3000.py", data["rules"])[1] == "preserve-and-reconcile"
    assert upstream_status.classify("ui/index.html", data["rules"])[1] == "port-and-regression"
    assert upstream_status.classify("new-unknown-file", data["rules"])[1] == "manual-review"


def test_windows_wrapper_does_not_start_tc_or_merge():
    text = (Path(__file__).parents[1] / "Check-ToneCommand-Upstream.ps1").read_text(encoding="utf-8")
    assert "tools/upstream_status.py" in text
    for forbidden in ("Start-Process", "git merge", "git reset", "git push", "server.py"):
        assert forbidden not in text
