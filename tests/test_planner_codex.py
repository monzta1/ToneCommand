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


@pytest.mark.parametrize('failure',['none','timeout','exit','empty','malformed','launch'])
def test_utf8_final_file_and_cleanup(monkeypatch,failure):
    monkeypatch.setattr(planner,'find_codex_cli',lambda:'codex.exe')
    monkeypatch.setenv('CODEX_CLI_MODEL','chosen-model')
    monkeypatch.setenv('ANTHROPIC_API_KEY','must-not-travel')
    paths=[]
    def run(args,**kw):
        path=Path(args[args.index('--output-last-message')+1]);paths.append(path)
        assert '--ephemeral' in args and args[args.index('--sandbox')+1]=='read-only'
        assert args[args.index('--model')+1]=='chosen-model'
        assert kw['encoding']=='utf-8' and '\u2192' in kw['input']
        assert 'CUSTOM AXEFX3' in kw['input'] and 'Fractal FM9' not in kw['input']
        assert 'ANTHROPIC_API_KEY' not in kw['env']
        if failure=='timeout':raise subprocess.TimeoutExpired(args,1)
        if failure=='launch':raise OSError('failed to start')
        if failure=='none':path.write_text(json.dumps({'name':'AI-Test'}),encoding='utf-8')
        if failure=='malformed':path.write_text('not json',encoding='utf-8')
        return subprocess.CompletedProcess(args,1 if failure=='exit' else 0,'progress not a plan','private diagnostic')
    monkeypatch.setattr(planner.subprocess,'run',run)
    if failure=='none':
        result,model=planner._plan_via_codex('amp \u2192 cab','state','ref',system='CUSTOM AXEFX3',shape='JSON')
        assert result=={'name':'AI-Test'} and model=='chosen-model'
    else:
        with pytest.raises(planner.BackendFailure) as error:
            planner._plan_via_codex('amp \u2192 cab','state','ref',system='CUSTOM AXEFX3',shape='JSON')
        assert 'private diagnostic' not in str(error.value)
    assert paths and not paths[0].exists()


def test_saved_codex_choice_and_optional_model(tmp_path,monkeypatch):
    monkeypatch.setenv('TONECOMMAND_AI_SETTINGS',str(tmp_path/'settings.json'))
    monkeypatch.setattr(ai_settings,'_APPLIED',{})
    monkeypatch.setattr(planner,'find_codex_cli',lambda:'codex.exe')
    saved=ai_settings.save({'backend':'codex','model':'chosen-model'})
    assert saved.backend=='codex' and planner.candidates()==['codex']
    assert ai_settings.planning_line()['service']=='ChatGPT via Codex CLI'
    assert ai_settings.list_models('codex')['models']==[]
    option=next(x for x in ai_settings.available_backends() if x['backend']=='codex')
    assert option['available'] and not option['needsKey'] and not option['needsBaseUrl']
    monkeypatch.setattr(planner,'find_codex_cli',lambda:None)
    assert not next(x for x in ai_settings.available_backends() if x['backend']=='codex')['available']
