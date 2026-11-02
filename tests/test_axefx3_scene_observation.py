"""Original-scene survey on independent fake ports, not native acceptance."""
from copy import deepcopy

import mido
import pytest

from devices.axefx3 import protocol as p
from devices.axefx3.scene_observation import SceneRecall, SceneSurvey, recalled
from fm9.device import ReadOnly
from tests.test_axefx3_official_amp_writer import OfficialPorts


class ScenePorts(OfficialPorts):
    def __init__(self):
        super().__init__()
        self.scene = 3
        self.recalls = []
        self.scene_fault = ''

    def answer(self, frame):
        if frame[5] == 19:
            body = [58, 0, 64 + 2 * (self.scene % 4) + int(self.scene % 2 == 1),
                    78, 1, 64 + 2 * ((self.scene + 1) % 4), 72, 1, 16, 73, 1, 16]
            return [p.envelope(19, body)[1:-1]]
        return super().answer(frame)

    def send(self, message):
        frame = message.bytes()
        if frame[5:8] == [1, 36, 0]:
            self.recalls.append(frame)
            if self.scene_fault == 'raise': raise OSError('Unknown transmission result')
            if self.scene_fault != 'ignore': self.scene = frame[12]
            if self.scene_fault == 'system': self.words[200][1] -= 1
            if self.scene_fault == 'unknown': self.words[206][1] -= 1
            if self.scene_fault == 'modifier': self.words[34][24] -= 1
            if self.scene_fault == 'amp': self.words[58][1] += 1
            if self.scene_fault == 'grid': self.cells[-1] = (4, 13, 0, True, 126)
            if self.scene_fault == 'preset': self.preset += 1
            if self.scene_fault == 'identity': self.identity = tuple(p.envelope(8,[33,1])[1:-1])
            return
        return super().send(message)


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('No real MIDI'))
    monkeypatch.setattr('devices.axefx3.scene_observation.time.sleep',lambda _:None)
    ports=ScenePorts();dev=SceneSurvey((ports.inp,ports.outp))
    yield dev,ports
    dev.close()


def test_survey_reads_actual_eight_maps_and_returns_original_scene_unchanged(device):
    dev,ports=device
    before=dev.capture().data()
    result=dev.survey(323,external_audio_muted=True,target_confirmed=True)
    assert result['state']==before and dev.capture().data()==before
    assert result['parameter_writes']==0 and not result['stored']
    assert result['scene_survey_verified'] and result['original_scene_returned']
    assert [m['scene'] for m in result['maps']]==list(range(1,9))
    assert [m['status'][0]['channel'] for m in result['maps']]==[0,1,2,3,0,1,2,3]
    assert [m['status'][0]['bypassed'] for m in result['maps']]==[False,True]*4
    assert len(ports.recalls)==9 and not ports.writes
    assert ports.scene==3


@pytest.mark.parametrize('fault',['system','unknown','modifier','amp','grid','preset','identity','raise','ignore'])
def test_unknown_recall_latches_and_does_not_retry_or_auto_restore(device,fault):
    dev,ports=device
    ports.scene_fault=fault
    with pytest.raises((ValueError,ReadOnly,OSError)):
        dev.survey(323,external_audio_muted=True,target_confirmed=True)
    assert len(ports.recalls)==1 and dev._uncertain and not ports.writes
    with pytest.raises(ReadOnly):dev.survey(323,external_audio_muted=True,target_confirmed=True)
    assert len(ports.recalls)==1


@pytest.mark.parametrize('arguments',[{},dict(external_audio_muted=True),dict(target_confirmed=True),
    dict(external_audio_muted=1,target_confirmed=True),dict(external_audio_muted=True,target_confirmed='yes')])
def test_mute_and_target_required_before_any_scene_io(device,arguments):
    dev,ports=device
    before=len(ports.sent)
    with pytest.raises(ReadOnly):dev.survey(323,**arguments)
    assert len(ports.sent)==before and not ports.recalls


@pytest.mark.parametrize('preset',[True,-1,1024,323.,'323'])
def test_target_type_and_capacity_are_strict_before_io(device,preset):
    dev,ports=device
    before=len(ports.sent)
    with pytest.raises(ReadOnly):dev.survey(preset,external_audio_muted=True,target_confirmed=True)
    assert len(ports.sent)==before and not ports.recalls


def test_different_selected_target_does_not_recall_a_scene(device):
    dev,ports=device
    with pytest.raises(ReadOnly):dev.survey(324,external_audio_muted=True,target_confirmed=True)
    assert not ports.recalls


@pytest.mark.parametrize('number',[True,0,9,-1,'2',2.])
def test_typed_recall_rejects_bad_numbers(number):
    with pytest.raises(ValueError):SceneRecall(number)


def test_raw_scene_frame_is_refused_and_typed_permit_is_consumed_once(device):
    dev,ports=device
    frame=SceneRecall(2).frame()
    with pytest.raises(ReadOnly):dev._send(frame)
    with dev.outp._scene_once(SceneRecall(2)):
        dev._send(frame)
        with pytest.raises(ReadOnly):dev._send(frame)
    assert len(ports.recalls)==1


def test_scene_permit_cannot_authorize_another_scene_or_parameter(device):
    dev,ports=device
    with dev.outp._scene_once(SceneRecall(2)):
        with pytest.raises(ReadOnly):dev._send(SceneRecall(3).frame())
        with pytest.raises(ReadOnly):dev._send(p.envelope(1,[9,0,*([0]*13)]))
    assert not ports.recalls and not ports.writes


def test_recall_validator_changes_only_scene_and_channel_bypass(device):
    dev,ports=device
    before=dev.capture().data();after=deepcopy(before)
    after['scene']=2;after['status'][0]['channel']=0;after['status'][0]['bypassed']=True
    recalled(before,after,2)
    after['bulk']['201'][0]-=1
    with pytest.raises(ValueError):recalled(before,after,2)


def test_survey_clears_a_previous_pending_scalar_review(device):
    dev,ports=device
    dev._review=object()
    dev.survey(323,external_audio_muted=True,target_confirmed=True)
    assert dev._review is None
