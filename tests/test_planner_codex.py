"""Direct CLI compatibility with no real AI calls or account access."""
import json
import subprocess
from pathlib import Path

import pytest

from fm9 import ai_settings, planner


def test_provider_does_not_duplicate_or_shadow_existing_planner_definitions():
    import ast
    from collections import Counter
    tree=ast.parse(Path(planner.__file__).read_text(encoding='utf-8'))
    names=[node.name for node in tree.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))]
    assert all(count==1 for count in Counter(names).values())
    assert names.count('find_codex_cli')==names.count('_plan_via_codex')==1
    assert names.count('plan')==names.count('plan_stream')==1


def test_cli_environment_keeps_windows_runtime_paths():
    runtime = {'PATH': 'C:/bin', 'SystemRoot': 'C:/Windows',
               'ComSpec': 'C:/Windows/System32/cmd.exe',
               'USERPROFILE': 'C:/Users/Player',
               'APPDATA': 'C:/Users/Player/AppData/Roaming',
               'LOCALAPPDATA': 'C:/Users/Player/AppData/Local'}
    source = dict(runtime, UNRELATED_SECRET='must-not-travel')
    assert planner.cli_env(planner.CODEX_ENV_KEYS, source) == runtime


def test_codex_environment_keeps_windows_paths_but_not_other_credentials(monkeypatch):
    # os.environ on Windows is case insensitive; exercise the real mapping too.
    monkeypatch.setenv('SystemRoot', 'C:/Windows')
    monkeypatch.setenv('USERPROFILE', 'C:/Users/Player')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'private-anthropic')
    monkeypatch.setenv('OPENAI_API_KEY', 'private-api-not-cli-login')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'private-aws')
    env = planner.cli_env(planner.CODEX_ENV_KEYS)
    assert env['SystemRoot'] == 'C:/Windows'
    assert env['USERPROFILE'] == 'C:/Users/Player'
    assert not {'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'AWS_SECRET_ACCESS_KEY'} & env.keys()


def test_explicit_codex_never_falls_back(monkeypatch):
    monkeypatch.setenv('PLANNER_BACKEND','codex')
    assert planner.candidates()==['codex']
    monkeypatch.setattr(planner,'find_codex_cli',lambda:None)
    with pytest.raises(RuntimeError,match='codex.*unavailable'):
        planner.plan('test','state','reference')
    monkeypatch.delenv('PLANNER_BACKEND')
    assert 'codex' not in planner.candidates()


def test_explicit_binary_path_is_authoritative(monkeypatch,tmp_path):
    monkeypatch.setenv('TONECOMMAND_CODEX_CLI',str(tmp_path/'missing.exe'))
    monkeypatch.setattr(planner.shutil,'which',lambda name:'other.exe')
    assert planner.find_codex_cli() is None
    binary=tmp_path/'codex.exe';binary.touch()
    monkeypatch.setenv('TONECOMMAND_CODEX_CLI',str(binary))
    assert planner.find_codex_cli()==str(binary)


def test_path_wins_without_scanning_editor_bundles(monkeypatch):
    monkeypatch.setattr(planner.shutil,'which',lambda name:'on-path')
    assert planner.find_codex_cli()=='on-path'


@pytest.mark.parametrize('platform_name,architecture,expected',[
    ('win32','AMD64','windows-x86_64'),('win32','ARM64','windows-aarch64'),
    ('win32','unsupported',None),('linux','AMD64',None)])
def test_windows_editor_resolver_uses_architecture_and_numeric_version(
        monkeypatch,tmp_path,platform_name,architecture,expected):
    monkeypatch.setattr(planner.sys,'platform',platform_name)
    monkeypatch.setattr(planner.platform,'machine',lambda:architecture)
    monkeypatch.setattr(planner.shutil,'which',lambda name:None)
    monkeypatch.setattr(planner.Path,'home',classmethod(lambda cls:tmp_path))
    for version in ('0.9.0','0.10.0','not-a-version'):
        binary=tmp_path/'.vscode/extensions'/('openai.chatgpt-'+version)/'bin/windows-x86_64/codex.exe'
        binary.parent.mkdir(parents=True);binary.touch()
    arm=tmp_path/'.vscode-insiders/extensions/openai.chatgpt-0.10.0/bin/windows-aarch64/codex.exe'
    arm.parent.mkdir(parents=True);arm.touch()
    found=planner.find_codex_cli()
    if expected:
        assert found and expected in found and '0.10.0' in found
    else:
        assert found is None


def test_suspended_runner_has_no_process_config_account_or_file_io(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('Suspended runner must not perform IO')
    monkeypatch.setattr(planner.subprocess,'run',forbidden)
    monkeypatch.setattr(planner.subprocess,'Popen',forbidden)
    monkeypatch.setattr(planner,'find_codex_cli',forbidden)
    monkeypatch.setattr(planner.tempfile,'mkstemp',forbidden)
    with pytest.raises(planner.BackendFailure,match='tool-free'):
        planner._plan_via_codex('prompt','state','reference')


@pytest.mark.parametrize('stream',['plan','converse'])
def test_stop_never_falls_back_to_a_blocking_codex_run(monkeypatch,stream):
    from threading import Event
    monkeypatch.setenv('PLANNER_BACKEND','codex')
    monkeypatch.setattr(planner,'plan',lambda *a:pytest.fail('Blocking fallback'))
    monkeypatch.setattr(planner,'converse',lambda *a:pytest.fail('Blocking fallback'))
    cancel=Event();cancel.set()
    with pytest.raises(planner.PlanCancelled):
        if stream=='plan':list(planner.plan_stream('prompt','state','ref',cancel=cancel))
        else:list(planner.converse_stream([{'role':'user','content':'prompt'}],'state','ref',cancel=cancel))


def test_saved_codex_choice_and_optional_model(tmp_path,monkeypatch):
    monkeypatch.setenv('TONECOMMAND_AI_SETTINGS',str(tmp_path/'settings.json'))
    monkeypatch.setattr(ai_settings,'_APPLIED',{})
    monkeypatch.setattr(planner,'find_codex_cli',lambda:'codex.exe')
    saved=ai_settings.save({'backend':'codex','model':'chosen-model'})
    assert saved.backend=='codex' and planner.candidates()==['codex']
    assert ai_settings.planning_line()['service']=='ChatGPT via Codex CLI'
    assert ai_settings.list_models('codex')['models']==[]
    option=next(x for x in ai_settings.available_backends() if x['backend']=='codex')
    assert not option['available'] and not option['needsKey'] and not option['needsBaseUrl']
    monkeypatch.setattr(planner,'find_codex_cli',lambda:None)
    assert not next(x for x in ai_settings.available_backends() if x['backend']=='codex')['available']
