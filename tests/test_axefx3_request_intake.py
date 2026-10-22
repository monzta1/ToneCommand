"""Clarifications are read-only scope choices, not unsupported write release."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import server
from devices.axefx3 import fw33_profile, request_intake as intake, scene_intent,wah_voicing
from tests.test_axefx3_album_build import device
from tests.test_axefx3_scene_counts import short_design

VAI = ('Steve vai for the love of god. graag 4 scenes waarbij het liedje volledig kan worden doorlopen. '
       'gebruik de juiste AMP / CAB combinatie en ook de wah zou een high pitch moeten geven als ik toe down doe. '
       'wah moet auto engaged worden op external 2.')
REG = SimpleNamespace(firmware=fw33_profile.KEY)


@pytest.mark.parametrize('text,expected', [
    ('graag 4 scenes', [4]), ('vier scènes voor dit lied', [4]), ('four scenes', [4]),
    ('SCENES: 8', [8]), ('scene 1 intro, scene 2 solo', []), ('eerste 20 seconden', []),
    ('4 scenes, liever 2 scenes', [2, 4]), ('9 scenes', [9]), ('0 scenes', [0]),
    ('two scenes with four scenes later', [2, 4]), ('één scene', [1]),
    ('-1 scenes', [-1]),
])
def test_explicit_counts_not_scene_numbers_or_audio_seconds(text, expected):
    assert intake.scene_counts(text) == expected


def test_vai_ambiguity_before_ai_and_controller_ack_after_route_choice():
    first = intake.analyze(VAI, REG, 'auto', 1)
    assert first['scenes'] == 4 and not first['ready']
    assert [q['id'] for q in first['questions']] == ['pitch_meaning']
    answer = intake.Resolution(pitch_meaning='filter')
    assert intake.analyze(VAI, REG, 'auto', 1, answer)['ready']
    route = intake.analyze(VAI, REG, 'amp', 1, answer)
    assert [q['id'] for q in route['questions']] == ['wah_controller']
    answer.accepted_omissions = ['wah_controller']
    result = intake.analyze(VAI, REG, 'amp', 1, answer)
    assert result['ready'] and result['scenes'] == 4
    assert result['approved_omissions'] == ['wah_controller']
    assert 'NEVER musical pitch' in intake.context(result)
    assert not result['hardware_written']


def test_real_pitch_is_separate_and_cannot_be_enabled_by_answer():
    result = intake.analyze(VAI, REG, 'amp', 4, intake.Resolution(pitch_meaning='pitch'))
    assert {q['id'] for q in result['questions']} == {'pitch', 'wah_controller'}
    reg = SimpleNamespace(firmware='32.06')
    result = intake.analyze('Whammy pitch shift', reg, 'amp', 1)
    assert [q['id'] for q in result['questions']] == ['pitch']


@pytest.mark.parametrize('prompt', ('4 scenes en 2 scenes', '9 scenes', '0 scenes'))
def test_conflicting_or_invalid_count_needs_explicit_selection(prompt):
    assert not intake.analyze(prompt, REG, 'amp', 3)['ready']
    result = intake.analyze(prompt, REG, 'amp', 3, intake.Resolution(scene_count_override=True))
    assert result['ready'] and result['scenes'] == 3


def test_route_limit_does_not_silently_shrink_four_scenes():
    result = intake.analyze('four scenes', REG, 'nam', 1)
    assert result['scenes'] == 4 and not result['ready']
    assert intake.analyze('four scenes', REG, 'nam', 2, intake.Resolution(scene_count_override=True))['ready']
    assert intake.analyze('4 scenes', REG, 'amp', 8, refining=True)['scenes'] == 8


def test_negated_effects_and_unrelated_scope_answers_do_not_omit_requirements():
    result = intake.analyze('4 scenes zonder wah, geen reverb en zonder pitch', REG, 'amp', 4)
    assert result['ready'] and not result['approved_omissions']
    result = intake.analyze('Wah on external 2', REG, 'amp', 4, intake.Resolution(accepted_omissions=['pitch']))
    assert not result['ready'] and not result['approved_omissions']


def test_off_effects_are_not_required_but_bright_wah_still_needs_verified_voicing():
    assert intake.analyze('wah uit, reverb off', REG, 'amp', 4)['ready']
    result=intake.analyze('heldere wah', REG, 'amp', 4)
    assert [q['id'] for q in result['questions']]==['wah_controller']


@pytest.mark.parametrize('payload', ({'allow_writes': True}, {'accepted_omissions': ['drive']},
                                     {'pitch_meaning': 'enable'}, {'scene_count_override': 'yes'}))
def test_resolution_is_strict_not_an_arbitrary_instruction_channel(payload):
    with pytest.raises(ValidationError):
        intake.Resolution.model_validate(payload)


@pytest.fixture
def workspace(monkeypatch):
    # Historical unavailable-capability path stays tested independently of
    # the newly accepted FW33 Wah builder.
    monkeypatch.setattr(wah_voicing,'RELEASED',False)
    dev = device(monkeypatch)
    monkeypatch.setattr(server, '_context', server.DeviceContext('axefx3', dev.reg, dev, 'Axe-Fx III'))
    monkeypatch.setattr(server, '_gig_mode', {'on': False})
    monkeypatch.setattr(server, '_plan_revisions', {})
    monkeypatch.setattr(server, '_audition', {'open': False})
    monkeypatch.setattr(server.ai_settings, 'apply_to_env', lambda: None)
    monkeypatch.setenv('PLANNER_BACKEND', 'cli')
    ask = Mock(side_effect=lambda *a, **kw: dict(**kw['validate'](deepcopy(short_design(4))), backend='cli', model='mock'))
    monkeypatch.setattr(server.planner, 'plan', ask)
    server._afx3_tone_reviews.clear()
    try:
        with TestClient(server.app) as client:
            yield client, dev, ask
    finally:
        server._afx3_tone_reviews.clear()
        server._afx3_tone_reviews.last_sent = None


def test_direct_api_cannot_skip_intake_or_obtain_send_ticket(workspace):
    client, dev, ask = workspace
    body = dict(prompt=VAI, expected_preset=322, scenes=1, mode='amp')
    for path in ('intake', 'plan'):
        response = client.post('/api/axefx3/' + path, json=body)
        assert response.status_code == 200, response.text
        result = response.json()
        assert not result.get('intake', result)['ready']
        assert 'token' not in result and 'actions' not in result
    options = client.post('/api/axefx3/options', json=dict(prompt=VAI, expected_preset=322))
    assert options.status_code == 200 and options.json()['needs_clarification']
    ask.assert_not_called()
    dev._write.assert_not_called()
    dev.set_scene.assert_not_called()
    dev.store_preset.assert_not_called()


def test_explicit_answers_build_four_scenes_with_visible_omission_only(workspace):
    client, dev, ask = workspace
    body = dict(prompt=VAI, expected_preset=322, scenes=1, mode='amp',
                resolution=dict(pitch_meaning='filter', accepted_omissions=['wah_controller']))
    response = client.post('/api/axefx3/plan', json=body)
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result['scenes']) == 4 and result['token']
    assert 'Exactly 4 scenes.' in ask.call_args.args[0]
    assert 'explicitly deferred requirements=wah_controller' in ask.call_args.kwargs['system']
    assert any('NOT executed' in w for w in result['warnings'])
    assert not any(a['kind'] == 'bind_controller' for a in result['actions'])
    dev._write.assert_not_called()
    dev.store_preset.assert_not_called()


def test_typed_design_validation_failure_is_not_a_backend_connection_error(workspace):
    client, dev, ask = workspace
    raw = short_design(4)
    raw['scene_goals'][0]['required_features'] = ['wah_controller']
    # Reproduce the shared planner wrapping validation as backend_error.
    def failed(*a, **kw):
        try:
            kw['validate'](raw)
        except scene_intent.MissingFeature as exc:
            raise RuntimeError('every planner backend failed: codex [backend_error]') from exc
    ask.side_effect = failed
    response = client.post('/api/axefx3/plan', json=dict(prompt='Four distinct guitar scenes', scenes=4, mode='amp', expected_preset=322))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['needs_clarification'] and 'token' not in result
    assert 'not an AI connection failure' in result['intake']['questions'][0]['text']
    dev._write.assert_not_called()


def test_intake_rechecks_target_and_never_grants_send_or_storage(workspace):
    client, dev, ask = workspace
    response = client.post('/api/axefx3/intake', json=dict(prompt=VAI, scenes=4, expected_preset=323))
    assert response.status_code == 409
    ask.assert_not_called()
    dev._write.assert_not_called()
    dev.store_preset.assert_not_called()


def test_unreadable_intake_target_is_a_readable_refusal(workspace):
    client, dev, ask = workspace
    dev.current_preset=lambda:None
    response=client.post('/api/axefx3/intake',json=dict(prompt=VAI,scenes=4,expected_preset=322))
    assert response.status_code==409 and 'unreadable' in response.text
    ask.assert_not_called()
    dev._write.assert_not_called()
