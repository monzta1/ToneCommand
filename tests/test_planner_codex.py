"""Direct CLI compatibility with no real AI calls or account access."""
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from fm9 import ai_settings, planner


@pytest.mark.parametrize('binary_keys', [planner.CODEX_ENV_KEYS,
                                       planner.CLAUDE_ENV_KEYS,
                                       planner.GROK_ENV_KEYS])
def test_cli_environment_keeps_windows_runtime_paths(binary_keys):
    runtime = {'PATH': 'C:/bin', 'SystemRoot': 'C:/Windows',
               'ComSpec': 'C:/Windows/System32/cmd.exe',
               'USERPROFILE': 'C:/Users/Player',
               'APPDATA': 'C:/Users/Player/AppData/Roaming',
               'LOCALAPPDATA': 'C:/Users/Player/AppData/Local'}
    source = dict(runtime, UNRELATED_SECRET='must-not-travel')
    assert planner.cli_env(binary_keys, source) == runtime


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
