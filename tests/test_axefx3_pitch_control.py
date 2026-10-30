"""Scripted Pitch octave-pedal output boundary, not hardware acceptance."""
from copy import deepcopy
from dataclasses import replace
import threading
from types import SimpleNamespace

import mido
import pytest

from fm9 import protocol as p
from devices.axefx3 import pitch_control as pitch, protocol, firmware_identity
from devices.axefx3.registry import Registry, SUPPORTED_FIRMWARE
from tests.test_axefx3_beta5_amp_calibration import IDENTITY


class Rig:
    def __init__(self):
        self._lock=threading.RLock();self._injected_ports=True
        self.reg=Registry(firmware_identity.BETA5_KEY);self.reg.hardware_variant='mk2'
        self.target,self.scene,self.identity=327,1,IDENTITY
        self.blocks=[p.BlockStatus(e,e==110,0,1 if e in (200,201) else 4)
            for e in (58,62,118,110,206,200,201)]
        self.cells=[p.GridCell(0,i,e,False,0) for i,e in enumerate((58,62,118,110,206))]
        self.words={e:[0]*n for e,n in ((58,568),(62,424),(118,176),(110,464),(206,72),(200,1525),(201,350))}
        self.words[200][100]=65535  # Valid opaque controller sentinel, never a write range.
        self.words[110][0]=9;self.words[110][3]=self.words[110][38]=65534
        self.words[110][16]=12;self.words[110][35]=2;self.words[110][39]=52427
        self.mods=[list(pitch.DEFAULT_MODIFIER) for _ in range(32)]
        for w in self.mods:w[8]=0;w[9]=78
        self.frames=[];self.fault='';self.outp=Port(self)
    def _request(self,frame,parse):
        assert frame==protocol.envelope(8,[])
        assert parse(protocol.envelope(1,[48,0,0,0,0,0,6,0,0,0,0,0,0,0,0])[1:-1]) is None
        return parse(self.identity)
    def current_preset(self):return self.target,'Pitch fixture'
    def current_scene(self):return self.scene
    def status_dump(self):return self.blocks.copy()
    def read_grid(self):return self.cells.copy()
    def bulk_read(self,eid):return self.words[eid].copy()
    def read_modifier(self,n):return self.mods[n-1].copy()
    def scene_name(self,n):return n,'Scene '+str(n)
    def read_display_text(self,eid,pid):
        assert eid==110
        words=self.words[110]
        if pid==44:return 'BYPASSED' if next(b.bypassed for b in self.blocks if b.effect_id==110) else 'ENGAGED'
        if pid in (3,38):return f'{words[pid]/65534*100:.1f} %'
        if pid==39:return f'{words[39]/65534*100-80:.1f} dB'
        return str(words[pid])


class Port:
    closed=False
    def __init__(self,rig):self.rig=rig
    def send(self,message):
        r=self.rig;frame=message.bytes();r.frames.append(frame)
        if r.fault=='transport':raise OSError('Outcome unknown')
        if r.fault=='interrupt':raise KeyboardInterrupt()
        data=frame[6:-2];eid=p.decode14(*data[2:4])
        if data[:2]==[58,0]:
            free=next(i for i,w in enumerate(r.mods) if w[0]==w[8]==0)
            r.mods[free]=list(pitch.DEFAULT_MODIFIER)
        elif data[:2]==[59,0]:
            r.mods[eid-3]=list(pitch.DEFAULT_MODIFIER);r.mods[eid-3][8]=0
        else:
            assert data[:2]==[9,0]
            pid=p.decode14(*data[4:6]);value=p.decode_f32_septets(data[6:11])
            if eid in range(3,35):r.mods[eid-3][pid]=int(value)
            elif pid==0:
                r.words[110][0]=int(value);r.words[110][38]=65534 if value==9 else 32767
                if value==9:r.words[110][35]=2
            elif pid==44:r.blocks=[replace(b,bypassed=bool(value)) if b.effect_id==110 else b for b in r.blocks]
            elif pid in (15,16):r.words[110][pid]=int(value)
            elif pid==39:r.words[110][39]=round((value+80)/100*65534)
            else:r.words[110][pid]=round(value*65534)
        if r.fault=='other_block':r.words[58][10]+=1
        if r.fault=='other_channel':r.words[110][120]+=1
        if r.fault=='modifier':r.mods[31][9]+=1
        if r.fault=='identity':r.identity=tuple([*IDENTITY[:-1],0])


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(pitch.time,'sleep',lambda _:None)
    return Rig()


def apply(rig,request):
    w=pitch.Writer(rig,calibration=True)
    review,before=w.prepare(request)
    result=w.apply(review,external_audio_muted=True,target_confirmed=True)
    return w,before,result


def test_read_only_observation_handles_opaque_sentinel_and_all_modifier_words(rig):
    w=pitch.Writer(rig,calibration=True);state=w.observe()
    assert state['bulk']['200'][100]==65535 and state['modifiers'][0][9]==78
    assert not rig.frames
    assert firmware_identity.BETA5_KEY not in SUPPORTED_FIRMWARE


@pytest.mark.parametrize('step',[
    pitch.Step('stop',6),pitch.Step('start',6),pitch.Step('control',50),
    pitch.Step('mix',50),pitch.Step('level',-12),pitch.Step('bypass',0),pitch.Step('model',0)])
def test_single_captured_calibration_step_preserves_every_other_surface(rig,step):
    w,before,result=apply(rig,step)
    assert result['ok'] and not result['stored'] and len(rig.frames)==1
    assert not getattr(rig,'_pitch_uncertain',False)
    assert w.observe()==w.expected(before,w.observe(),step)


def test_setup_stages_then_allocates_real_curve_and_uses_selected_source_only_on_a(rig):
    before=deepcopy(rig.words)
    w,_,result=apply(rig,pitch.Setup(13))
    assert result['ok'] and not result['stored']
    assert rig.mods[0][0]==13 and rig.mods[0][8:10]==[110,3] and rig.mods[0][17]==1
    assert pitch.curve(rig.mods[0]) and rig.mods[0][10]==0
    assert rig.words[110][15:17]==[0,12] and rig.words[110][38]==65534
    assert rig.words[110][39]==52427
    assert not next(b.bypassed for b in rig.blocks if b.effect_id==110)
    assert rig.words[110][116:]==before[110][116:]
    assert all(rig.words[e]==words for e,words in before.items() if e!=110)
    assert not any(f[5] in (10,12,13,14) for f in rig.frames)


def test_existing_curve_and_unrelated_modifier_are_preserved_without_reallocation(rig):
    rig.mods[0][0]=12;rig.mods[0][8]=94;rig.mods[0][9]=5
    rig.mods[6]=list(pitch.DEFAULT_MODIFIER);rig.mods[6][0]=13
    preserved=deepcopy(rig.mods)
    _,_,result=apply(rig,pitch.Setup(12,engage=False))
    assert result['ok'] and rig.mods[0]==preserved[0] and rig.mods[6][0]==12
    assert rig.mods[6][17]==1
    assert all(rig.mods[i]==preserved[i] for i in range(32) if i!=6)
    assert not any(f[6:8]==[58,0] for f in rig.frames)
    assert next(b.bypassed for b in rig.blocks if b.effect_id==110)


def test_native_allocation_chooses_free_slot_and_never_clears_residual_metadata(rig):
    for i in (0,1):rig.mods[i][0]=12;rig.mods[i][8]=94+i;rig.mods[i][9]=5
    preserved=deepcopy(rig.mods)
    _,_,result=apply(rig,pitch.Setup(12))
    assert result['ok'] and rig.mods[:2]==preserved[:2]
    assert rig.mods[2][8:10]==[110,3] and rig.mods[2][0]==12
    assert rig.mods[3:]==preserved[3:]


def test_full_modifier_list_refuses_before_even_quiet_staging(rig):
    for w in rig.mods:w[0]=12;w[8]=94;w[9]=5
    w=pitch.Writer(rig,calibration=True)
    with pytest.raises(ValueError,match='free modifier slot'):
        w.prepare(pitch.Setup(13))
    assert not rig.frames and w.pending is None


def test_unmeasured_starting_model_refuses_before_quiet_staging(rig):
    rig.words[110][0]=15
    with pytest.raises(ValueError,match='other model transitions are unverified'):
        pitch.Writer(rig,calibration=True).prepare(pitch.Setup(13))
    assert not rig.frames


def test_model_selection_preserves_quiet_level_and_other_channels(rig):
    rig.words[110][0]=0;rig.words[110][38]=32767
    _,_,result=apply(rig,pitch.Setup(12))
    assert result['ok']
    setters=[(f[8]+128*f[9],f[10]+128*f[11],p.decode_f32_septets(f[12:17]))
        for f in rig.frames if f[6:8]==[9,0]]
    assert setters.index((110,39,-12.))<setters.index((110,0,9.))<setters.index((110,39,0.))


def test_newly_inserted_dual_detune_model_default_is_accounted_for(rig):
    rig.words[110][0]=0;rig.words[110][35]=1;rig.words[110][38]=16384
    preserved=deepcopy(rig.words)
    w,_,result=apply(rig,pitch.Setup(13))
    assert result['ok'] and rig.words[110][0]==9 and rig.words[110][35]==2
    assert rig.words[110][38:40]==[65534,52427]
    assert rig.words[110][116:]==preserved[110][116:]
    assert all(rig.words[e]==words for e,words in preserved.items() if e!=110)


def test_unmeasured_model_default_refuses_before_even_bypass_staging(rig):
    rig.words[110][0]=0;rig.words[110][35]=4
    with pytest.raises(ValueError,match='word35'):
        pitch.Writer(rig).prepare(pitch.Setup(13))
    assert not rig.frames


def test_rounded_display_does_not_hide_a_different_bulk_word(rig):
    rig.words[110][39]-=1  # Still shows 0.0dB; not the exact captured zero word.
    _,_,result=apply(rig,pitch.Setup(13))
    assert result['ok'] and rig.words[110][39]==52427


def test_expiry_after_one_write_stops_remaining_steps_and_latches(rig):
    now=[0.];w=pitch.Writer(rig,calibration=True,clock=lambda:now[0])
    review,_=w.prepare(pitch.Setup(13));send=rig.outp.send
    def expire(message):
        send(message);now[0]=61.
    rig.outp.send=expire
    with pytest.raises(pitch.PitchReadbackError,match='expired'):
        w.apply(review,external_audio_muted=True,target_confirmed=True)
    assert len(rig.frames)==1 and rig._pitch_uncertain


def test_background_thread_cannot_use_an_owning_thread_permit(rig):
    w=pitch.Writer(rig,calibration=True);step=pitch.Step('stop',6)
    review,_=w.prepare(step);w.active=True;w._executing=review;w._active_step=step
    refused=[]
    def worker():
        try:w.output.send(mido.Message('sysex',data=step.frame()[1:-1]))
        except PermissionError:refused.append(True)
    with w.output.once(step,None):
        t=threading.Thread(target=worker);t.start();t.join()
    assert refused==[True] and not rig.frames


@pytest.mark.parametrize('change',['preset','scene','channel','identity','modifiers','other_block','grid'])
def test_context_drift_before_send_refuses_without_a_set(rig,change):
    w=pitch.Writer(rig,calibration=True);review,_=w.prepare(pitch.Setup(12))
    if change=='preset':rig.target=328
    if change=='scene':rig.scene=2
    if change=='channel':rig.blocks=[replace(b,channel=1) if b.effect_id==110 else b for b in rig.blocks]
    if change=='identity':rig.identity=tuple([*IDENTITY[:-1],0])
    if change=='modifiers':rig.mods[31][9]+=1
    if change=='other_block':rig.words[58][100]+=1
    if change=='grid':rig.cells[0]=replace(rig.cells[0],cable_in_mask=1)
    with pytest.raises((ValueError,PermissionError)):
        w.apply(review,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames


@pytest.mark.parametrize('fault',['transport','interrupt','other_block','other_channel','modifier','identity'])
def test_uncertainty_is_connection_wide_and_never_retries_or_restores(rig,fault):
    rig.fault=fault;w=pitch.Writer(rig,calibration=True)
    review,_=w.prepare(pitch.Step('stop',6))
    with pytest.raises((pitch.PitchReadbackError,KeyboardInterrupt)):
        w.apply(review,external_audio_muted=True,target_confirmed=True)
    assert len(rig.frames)==1 and rig._pitch_uncertain
    with pytest.raises(PermissionError):pitch.Writer(rig,calibration=True).observe()


def test_false_or_missing_consents_never_send(rig):
    for muted,target in ((True,False),(False,True),(1,True),(True,1)):
        w=pitch.Writer(rig,calibration=True);review,_=w.prepare(pitch.Setup(12))
        with pytest.raises(PermissionError):w.apply(review,external_audio_muted=muted,target_confirmed=target)
    assert not rig.frames


def test_review_is_owned_single_use_and_expires(rig):
    now=[0.];w=pitch.Writer(rig,calibration=True,clock=lambda:now[0])
    review,_=w.prepare(pitch.Step('stop',6));now[0]=61.
    with pytest.raises(PermissionError):w.apply(review,external_audio_muted=True,target_confirmed=True)
    with pytest.raises(ValueError):w.apply(review,external_audio_muted=True,target_confirmed=True)
    assert not rig.frames
    other=pitch.Writer(rig,calibration=True)
    review,_=other.prepare(pitch.Step('stop',6))
    with pytest.raises(ValueError):w.apply(review,external_audio_muted=True,target_confirmed=True)


def test_generic_frames_cannot_arm_pitch_output(rig):
    w=pitch.Writer(rig,calibration=True)
    with pytest.raises(PermissionError):
        with w.output.once(protocol.param_frame(206,0,250,opcode=9),None):pass
    with pytest.raises(PermissionError):w.output.send(mido.Message('control_change',control=6,value=127))
    assert not rig.frames


@pytest.mark.parametrize('source',[0,10,11,14,True,12.0,'External 1'])
def test_source_is_user_selected_external_only(source):
    with pytest.raises(ValueError):pitch.Setup(source)


@pytest.mark.parametrize('step',[('model',8),('level',1),('stop',24),('stop',-12),
    ('source',14),('control',1),('channel',2),('unknown',0),('bypass',True)])
def test_only_captured_literals_exist(step):
    with pytest.raises(ValueError):pitch.Step(*step)


def test_wrong_firmware_chassis_or_unmeasured_curve_cannot_be_promoted(rig,monkeypatch):
    monkeypatch.setattr(pitch,'RELEASED',True)
    assert pitch.supported(rig)
    for field,value in (('firmware','32.06'),('firmware','33.00'),('hardware_variant','mk1')):
        old=getattr(rig.reg,field);setattr(rig.reg,field,value)
        assert not pitch.supported(rig)
        with pytest.raises(PermissionError):pitch.Writer(rig)
        setattr(rig.reg,field,old)
    rig.mods[0]=list(pitch.DEFAULT_MODIFIER);rig.mods[0][5]=0
    with pytest.raises(ValueError):pitch.Writer(rig).observe()
    assert not rig.frames


def test_port_bytes_are_pinned_to_independent_editor_literals(rig):
    _,_,_=apply(rig,pitch.Step('stop',6))
    assert rig.frames==[list(bytes.fromhex('f0 00 01 74 10 01 09 00 6e 00 10 00 00 00 00 06 04 00 00 00 00 61 f7'))]
    assert pitch.Step('allocate',None).frame()==list(bytes.fromhex('f0 00 01 74 10 01 3a 00 6e 00 03 00 00 00 00 00 00 00 00 00 00 43 f7'))
    assert pitch.Step('source',13).frame(1)==list(bytes.fromhex('f0 00 01 74 10 01 09 00 03 00 00 00 00 00 40 0a 04 00 00 00 00 50 f7'))
