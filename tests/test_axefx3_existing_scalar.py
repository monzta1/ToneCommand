"""Eight original maps and minimal deltas, independent fake ports only."""
from copy import deepcopy
from dataclasses import replace
import struct

import mido
import pytest

from devices.axefx3 import protocol as p
from devices.axefx3.existing_scalar import ExistingEditor, ScalarWrite, DeltaReview
from fm9.device import ReadOnly
from tests.test_axefx3_scene_observation import ScenePorts


class ExistingPorts(ScenePorts):
    def __init__(self):
        super().__init__()
        self.scene = 0
        self.words[58][142] = 121
        self.words[58][143] = self.words[58][145] = 32767
        self.bypassed_first = False
        self.changed_inactive_map = False

    def answer(self, frame):
        if frame[5] == 19:
            return [p.envelope(19,[58,0,64+2*(self.scene%2)+int(self.scene==0 and self.bypassed_first or self.scene==4 and self.changed_inactive_map),
                78,1,64,72,1,16,73,1,16])[1:-1]]
        return super().answer(frame)

    def send(self, message):
        frame=message.bytes()
        if frame[5:8]==[1,9,0]:
            self.writes.append(frame)
            if self.behavior=='raise':raise OSError('Unknown transport result')
            if self.behavior=='ignore':return
            assert frame[8:10]==[58,0] and frame[10] in (1,3)
            value=struct.unpack('<f',sum(b<<(i*7) for i,b in enumerate(frame[12:17])).to_bytes(4,'little'))[0]
            self.words[58][(self.scene%2)*142+frame[10]]=round(value*65534)
            if self.behavior=='other_channel':self.words[58][2*142+frame[10]]+=1
            if self.behavior=='system':self.words[200][1]-=1
            if self.behavior=='modifier':self.words[34][24]-=1
            if self.behavior=='unknown':self.words[206][1]-=1
            if self.behavior=='preset':self.preset+=1
            return
        if frame[5:8]==[1,16,0]:
            pid=frame[10]
            text='WRONG' if self.behavior=='bad_display' and self.writes else f'{self.words[58][(self.scene%2)*142+pid]/65534*10:.2f}'
            bits=''.join(f'{b:08b}' for b in (text+'\0').encode())
            bits=bits.ljust((len(bits)+6)//7*7,'0');data=[int(bits[i:i+7],2) for i in range(0,len(bits),7)]
            reply=p.envelope(1,[16,0,58,0,pid,0,*([0]*7),len(data),0,*data])[1:-1]
            self.sent.append(frame);self.queue.append(mido.Message('sysex',data=reply));return
        return super().send(message)


def design():
    return dict(summary='Add body and controlled drive while preserving the existing rig.',
        scene_goals=[dict(scene=n,target=f'Keep original scene {n} role with more body.') for n in range(1,9)],
        changes=[dict(effect_id=58,channel=ch,parameter=param,value=value,reason='More body and controlled saturation.')
            for ch,param,value in [('A','DISTORT_DRIVE',3.4),('A','DISTORT_MID',5.6),
                                   ('B','DISTORT_DRIVE',5.4),('B','DISTORT_MID',5.8)]])


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('No physical MIDI'))
    monkeypatch.setattr('devices.axefx3.scene_observation.time.sleep',lambda _:None)
    ports=ExistingPorts();dev=ExistingEditor((ports.inp,ports.outp))
    yield dev,ports
    dev.close()


def scan(dev):
    return dev.scan(323,external_audio_muted=True,target_confirmed=True)


def test_actual_shared_channel_impacts_and_full_preservation(device):
    dev,ports=device
    before=dev.capture().data();reference=scan(dev)
    assert 'observed_state' not in reference and 'bulk' not in str(reference.keys())
    review=dev.prepare_delta(design());preview=review.preview()
    assert not preview['executable'] and not ports.writes
    assert preview['changes'][0]['affected_scenes']==[1,3,5,7]
    assert preview['changes'][2]['active_scenes']==[2,4,6,8]
    out=dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert out['verified'] and out['sent']==4 and out['scene_maps_verified']==8
    assert not out['stored'] and not out['undo_available'] and out['original_scene_returned']
    after=dev.capture().data();wanted=deepcopy(before)
    for ch,pid in [(0,1),(0,3),(1,1),(1,3)]:wanted['bulk']['58'][ch*142+pid]=after['bulk']['58'][ch*142+pid]
    assert wanted==after and len(ports.writes)==4
    with pytest.raises(ReadOnly):dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert len(ports.writes)==4


@pytest.mark.parametrize('fault',['raise','ignore','system','unknown','modifier','other_channel','bad_display','preset'])
def test_failed_delta_stops_before_later_changes_and_latches(device,fault):
    dev,ports=device;scan(dev);review=dev.prepare_delta(design());ports.behavior=fault
    with pytest.raises((ReadOnly,RuntimeError,ValueError,OSError)):
        dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert len(ports.writes)==1 and dev._uncertain
    with pytest.raises(ReadOnly):dev.prepare_delta(design())
    assert len(ports.writes)==1


@pytest.mark.parametrize('fault',['model','owner','source_none_owner','no_op','out_of_range','large_step',
    'other_effect','level','uncovered_scene','extra','changed_context'])
def test_unqualified_or_incoherent_design_cannot_authorize_set(device,fault):
    dev,ports=device
    if fault=='model':ports.words[58][142]=14
    if fault in ('owner','source_none_owner'):
        ports.words[3][8:10]=[58,1];ports.words[3][0]=13 if fault=='owner' else 0
    if fault=='uncovered_scene':ports.bypassed_first=True
    scan(dev);raw=design()
    if fault=='no_op':raw['changes'][0]['value']=ports.words[58][1]/65534*10
    elif fault=='out_of_range':raw['changes'][0]['value']=9.
    elif fault=='large_step':raw['changes'][0]['value']=4.4
    elif fault=='other_effect':raw['changes'][0]['effect_id']=62
    elif fault=='level':raw['changes'][0]['parameter']='DISTORT_LEVEL'
    elif fault=='extra':raw['frames']=[[1,2,3]]
    elif fault=='changed_context':ports.words[201][0]-=1
    with pytest.raises((ValueError,ReadOnly)):dev.prepare_delta(raw)
    assert not ports.writes


@pytest.mark.parametrize('consent',[{},dict(external_audio_muted=True),dict(target_confirmed=True),
    dict(external_audio_muted=1,target_confirmed=True)])
def test_consents_are_strict_and_consumed_before_any_execution(device,consent):
    dev,ports=device;scan(dev);review=dev.prepare_delta(design());recalls=len(ports.recalls)
    with pytest.raises(ReadOnly):dev.apply_delta(review,**consent)
    assert len(ports.recalls)==recalls and not ports.writes
    with pytest.raises(ReadOnly):dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)


def test_copied_or_superseded_review_is_not_connection_owned(device):
    dev,ports=device;scan(dev);review=dev.prepare_delta(design())
    with pytest.raises(ReadOnly):dev.apply_delta(replace(review),external_audio_muted=True,target_confirmed=True)
    assert not ports.writes
    old=dev.prepare_delta(design());dev.prepare_delta(design())
    with pytest.raises(ReadOnly):dev.apply_delta(old,external_audio_muted=True,target_confirmed=True)
    assert not ports.writes


def test_changed_scene_map_is_caught_by_fresh_pre_send_survey(device):
    dev,ports=device;scan(dev);review=dev.prepare_delta(design())
    ports.changed_inactive_map=True  # Current scene is unchanged: only a fresh full survey detects it.
    with pytest.raises(ReadOnly):dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert not ports.writes


def test_expired_review_refuses_before_any_scene_or_scalar_io(device,monkeypatch):
    import time
    dev,ports=device;scan(dev);review=dev.prepare_delta(design())
    calls=len(ports.sent);recalls=len(ports.recalls);now=time.monotonic()
    monkeypatch.setattr('devices.axefx3.existing_scalar.time.monotonic',lambda:now+300)
    with pytest.raises(ReadOnly):dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert len(ports.sent)==calls and len(ports.recalls)==recalls and not ports.writes


def test_unrequested_modifiers_remain_opaque(device):
    dev,ports=device;ports.words[34][8:10]=[70,2];ports.words[34][0]=13
    before=dev.capture().data()['modifiers'];scan(dev);review=dev.prepare_delta(design())
    assert dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)['verified']
    assert dev.capture().data()['modifiers']==before


@pytest.mark.parametrize('args',[(True,0,'DISTORT_DRIVE',3.4),(0,14,'DISTORT_DRIVE',3.4),
    (2,0,'DISTORT_DRIVE',3.4),(1,121,'DISTORT_LEVEL',-12.),(0,0,'DISTORT_MID',True),
    (0,0,'DISTORT_DRIVE',3.45)])
def test_typed_scalar_is_not_an_arbitrary_parameter_or_channel(args):
    with pytest.raises(ValueError):ScalarWrite(*args)


def test_direct_raw_scalar_is_refused_at_final_output(device):
    dev,ports=device
    edit=ScalarWrite(0,0,'DISTORT_DRIVE',3.4)
    with pytest.raises(ReadOnly):dev._send(edit.frame())
    assert not ports.writes


def test_preparation_without_real_scan_has_no_io(device):
    dev,ports=device;before=len(ports.sent)
    with pytest.raises(ReadOnly):dev.prepare_delta(design())
    assert len(ports.sent)==before and not ports.recalls


def test_scan_failure_after_survey_completion_latches_and_discards_context(device,monkeypatch):
    dev,ports=device
    with monkeypatch.context() as patch:
        def fail():raise OSError('reference unavailable after completed mutating survey')
        patch.setattr(dev,'reference',fail)
        with pytest.raises(OSError):scan(dev)
    assert dev._uncertain and dev._scan is None and dev._delta is None
    recalls=len(ports.recalls)
    with pytest.raises(ReadOnly):scan(dev)
    assert len(ports.recalls)==recalls


@pytest.mark.parametrize('stage',['recall','preflight'])
def test_expiry_during_preflights_cannot_arm_one_more_set(device,monkeypatch,stage):
    import time
    dev,ports=device;scan(dev);review=dev.prepare_delta(design())
    now=[review._expires-1];ready=[False];after_recall=[False]
    old_survey,old_recall,old_capture=dev.survey,dev._recall,dev.capture
    def survey(*args,**kwargs):
        value=old_survey(*args,**kwargs);ready[0]=True;return value
    def recall(*args):
        value=old_recall(*args)
        if ready[0]:
            after_recall[0]=True
            if stage=='recall':now[0]=review._expires
        return value
    def capture(*args,**kwargs):
        value=old_capture(*args,**kwargs)
        if after_recall[0] and stage=='preflight':now[0]=review._expires
        return value
    monkeypatch.setattr(time,'monotonic',lambda:now[0])
    monkeypatch.setattr(dev,'survey',survey);monkeypatch.setattr(dev,'_recall',recall)
    monkeypatch.setattr(dev,'capture',capture)
    monkeypatch.setattr(dev.outp,'_scalar_once',lambda *a:pytest.fail('Expired review armed a scalar permit'))
    with pytest.raises(ReadOnly,match='expired'):
        dev.apply_delta(review,external_audio_muted=True,target_confirmed=True)
    assert not ports.writes and dev._uncertain and dev._delta is None


def test_final_output_rechecks_expiry_after_permit_was_armed(device,monkeypatch):
    import time
    dev,ports=device;now=[10.]
    monkeypatch.setattr(time,'monotonic',lambda:now[0])
    edit=ScalarWrite(0,0,'DISTORT_DRIVE',3.4)
    with dev.outp._scalar_once(edit,11.):
        now[0]=11.
        with pytest.raises(ReadOnly,match='expired'):dev._send(edit.frame())
        assert dev.outp._scalar_permit is None
    assert not ports.writes
