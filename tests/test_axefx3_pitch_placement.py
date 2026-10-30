"""Independent scripted context and literal-port checks, not native proof."""
from dataclasses import replace
import threading

import mido
import pytest
from devices.axefx3 import pitch_placement as place
from fm9 import protocol as p
from tests.test_axefx3_pitch_control import Rig


CURSOR=list(bytes.fromhex('f0 00 01 74 10 01 30 00 00 00 00 00 06 00 00 00 00 00 00 00 00 22 f7'))
INSERT=list(bytes.fromhex('f0 00 01 74 10 01 32 00 6e 00 00 00 17 00 00 00 00 00 00 00 00 5f f7'))


class Fixture(Rig):
    def __init__(self):
        super().__init__()
        self.blocks=[b for b in self.blocks if b.effect_id in (58,200,201)]
        self.cells=[p.GridCell(0,0,58,False,0)]
        self.words={e:self.words[e] for e in (58,200,201)}
        self.level=-12.;self.outp=GridPort(self)

    def read_display_text(self,eid,pid):
        assert (eid,pid)==(58,21)
        return f'{self.level:.1f} dB'


class GridPort:
    closed=False
    def __init__(self,rig):self.rig=rig
    def send(self,message):
        r=self.rig;frame=message.bytes();r.frames.append(frame)
        assert type(message) is mido.Message and frame in (CURSOR,INSERT)
        if frame==CURSOR:
            if r.fault=='cursor_transport':raise OSError('Cursor outcome unknown')
            if r.fault=='target_after_cursor':r.target=328
            return
        if r.fault=='ignore':return
        r.blocks.append(p.BlockStatus(110,False,0,4))
        r.cells.append(p.GridCell(1 if r.fault=='position' else 0,1,110,False,0))
        r.words[110]=[0]*464
        if r.fault=='transport':raise OSError('Insertion outcome unknown')
        if r.fault=='interrupt':raise KeyboardInterrupt()
        if r.fault=='other_channel':r.words[58][143]+=1
        if r.fault=='controller':r.words[200][10]+=1
        if r.fault=='modifier':r.mods[0][10]+=1


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('devices.axefx3.pitch_placement.time.sleep',lambda _:None)
    rig=Fixture();host={'dev':rig,'gig':False}
    writer=place.Writer(rig,host_lock=threading.Lock(),selected=lambda:host['dev'],
        gig_locked=lambda:host['gig'],calibration=True)
    return rig,writer,host


def test_literal_placement_is_explicit_and_preserves_all_old_state(device):
    rig,writer,host=device;review,before=writer.prepare(place.Request(327))
    assert rig.frames==[]
    assert writer.apply(review,external_audio_muted=True,target_confirmed=True)==dict(
        verified=True,sent=True,stored=False,already_present=False)
    assert rig.frames==[CURSOR,INSERT] and place.Writer.matches(before,writer.observe())
    with pytest.raises(ValueError):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert len(rig.frames)==2


def test_existing_exact_pitch_is_a_verified_noop_not_recreation(device):
    rig,writer,host=device;first,_=writer.prepare(place.Request(327))
    writer.apply(first,external_audio_muted=True,target_confirmed=True)
    before=writer.observe();review,_=writer.prepare(place.Request(327))
    assert writer.apply(review,external_audio_muted=True,target_confirmed=True)['sent'] is False
    assert len(rig.frames)==2 and writer.observe()==before


@pytest.mark.parametrize('value',[True,326,328,-1,1024,'327',327.0,None])
def test_target_is_not_coerced_or_broadened(value):
    with pytest.raises(ValueError):place.Request(value)


@pytest.mark.parametrize('field,value',[('external_audio_muted',False),('external_audio_muted',1),
    ('target_confirmed',False),('target_confirmed','yes')])
def test_missing_exact_confirmation_consumes_review_before_any_frame(device,field,value):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327))
    args=dict(external_audio_muted=True,target_confirmed=True);args[field]=value
    with pytest.raises(PermissionError):writer.apply(review,**args)
    with pytest.raises(ValueError):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames


@pytest.mark.parametrize('change',['connection','gig','firmware','chassis','identity','preset','scene',
    'model','level','grid','modifier','controller','closed'])
def test_stale_or_unsupported_context_never_places(device,change):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327))
    if change=='connection':host['dev']=object()
    if change=='gig':host['gig']=True
    if change=='firmware':rig.reg.firmware='32.06'
    if change=='chassis':rig.reg.hardware_variant='mk1'
    if change=='identity':rig.identity=(*rig.identity[:-1],0)
    if change=='preset':rig.target=328
    if change=='scene':rig.scene=2
    if change=='model':rig.words[58][0]=14
    if change=='level':rig.level=-6
    if change=='grid':rig.cells.append(p.GridCell(0,2,None,True,0))
    if change=='modifier':rig.mods[0][8]=94
    if change=='controller':rig.words[200][11]+=1
    if change=='closed':rig.outp.closed=True
    with pytest.raises((ValueError,PermissionError)):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames


@pytest.mark.parametrize('fault',['cursor_transport','target_after_cursor','ignore','transport',
    'position','other_channel','controller','modifier'])
def test_unknown_outcome_latches_without_repeating_or_restoring(device,fault):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327));rig.fault=fault
    with pytest.raises(place.PlacementReadbackError):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert rig._pitch_uncertain and len(rig.frames)==(1 if fault in ('cursor_transport','target_after_cursor') else 2)
    with pytest.raises(PermissionError):writer.prepare(place.Request(327))


def test_interrupt_after_insert_still_latches_the_connection(device):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327));rig.fault='interrupt'
    with pytest.raises(KeyboardInterrupt):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert rig._pitch_uncertain and rig.frames==[CURSOR,INSERT]


def test_expired_foreign_replaced_and_read_expiry_reviews(device,monkeypatch):
    rig,writer,host=device;clock=[10.];writer.clock=lambda:clock[0]
    first,_=writer.prepare(place.Request(327));second,_=writer.prepare(place.Request(327))
    with pytest.raises(ValueError):writer.apply(first,external_audio_muted=True,target_confirmed=True)
    with pytest.raises(ValueError):writer.apply(replace(second),external_audio_muted=True,target_confirmed=True)
    clock[0]=71.
    with pytest.raises(PermissionError):writer.apply(second,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames


def test_expiry_during_final_observation_stops_before_any_command(device,monkeypatch):
    rig,writer,host=device;clock=[10.];writer.clock=lambda:clock[0]
    review,_=writer.prepare(place.Request(327));original=writer.observe
    def slow_read():
        result=original();clock[0]=71.;return result
    monkeypatch.setattr(writer,'observe',slow_read)
    with pytest.raises(PermissionError):writer.apply(review,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames


def test_concurrent_send_can_insert_only_once(device):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327));results=[]
    def send():
        try:results.append(writer.apply(review,external_audio_muted=True,target_confirmed=True))
        except ValueError:results.append('consumed')
    jobs=[threading.Thread(target=send) for _ in range(2)]
    for job in jobs:job.start()
    for job in jobs:job.join()
    assert len(results)==2 and results.count('consumed')==1 and rig.frames==[CURSOR,INSERT]


def test_foreign_thread_and_wrong_frame_do_not_consume_the_owner_permit(device):
    rig,writer,host=device;review,_=writer.prepare(place.Request(327))
    writer.active=True;writer._executing=review;writer._step='insert';rejected=[]
    with writer.output.once('insert'):
        def other():
            try:writer.output.send(mido.Message('sysex',data=INSERT[1:-1]))
            except PermissionError:rejected.append(True)
        job=threading.Thread(target=other);job.start();job.join()
        with pytest.raises(PermissionError):writer.output.send(mido.Message('sysex',data=CURSOR[1:-1]))
        writer.output.send(mido.Message('sysex',data=INSERT[1:-1]))
        with pytest.raises(PermissionError):writer.output.send(mido.Message('sysex',data=INSERT[1:-1]))
    assert rejected==[True] and rig.frames==[INSERT]


def test_final_output_cannot_be_armed_or_used_outside_the_active_review(device):
    rig,writer,host=device
    with pytest.raises(PermissionError):
        with writer.output.once('insert'):pytest.fail('Unreviewed arm')
    with pytest.raises(PermissionError):writer.output.send(mido.Message('sysex',data=INSERT[1:-1]))
    assert not rig.frames


@pytest.mark.parametrize('calibration',[False,None,1,'yes'])
def test_normal_app_mode_is_not_silently_activated(calibration):
    with pytest.raises(PermissionError):place.Writer(Fixture(),host_lock=threading.Lock(),
        selected=lambda:None,gig_locked=lambda:False,calibration=calibration)
