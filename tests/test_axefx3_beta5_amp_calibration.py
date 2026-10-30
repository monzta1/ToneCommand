"""Independent scripted ports for the closed Beta5 experiment, not hardware."""
from copy import deepcopy
from dataclasses import replace
import threading

import mido
import pytest

from devices.axefx3 import beta5_amp_calibration as cal, protocol, fw33_profile
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import SUPPORTED_FIRMWARE
from fm9 import protocol as p


IDENTITY=tuple(bytes.fromhex('00 01 74 10 08 61 00 10 01 11 00 00 4f 63 74 20 32 36 20 32 30 32 36 20 31 32 3a 34 32 3a 34 35 00 00 00 00 00 00 00 00 00 00 00 00 02'))


class Port:
    def __init__(self):
        self.queue,self.sent=[],[]
        self.ident,self.target,self.scene=IDENTITY,327,1
        self.blocks=[p.BlockStatus(e,False,0,1 if e in (200,201) else 4) for e in cal.IDS]
        self.cells=[p.GridCell(0,i,e,False,0) for i,e in enumerate(cal.IDS[:5])]
        self.words={e:[0]*n for e,n in cal.WORDS.items()}
        self.words.update({e:[0]*25 for e in range(3,35)})
        self.words[3][9]=78  # Unused metadata must be preserved, not cleared.
        self.shown={1:5.,3:5.,21:-12.}
        for pid,value in self.shown.items():
            self.words[58][pid]=round((value+80)/100*65534) if pid==21 else round(value/10*65534)
        self.fault=''
    def close(self):pass
    def iter_pending(self):
        while self.queue:yield self.queue.pop(0)
    def reply(self,fn,payload):
        self.queue.append(mido.Message('sysex',data=protocol.envelope(fn,payload)[1:-1]))
    def send(self,message):
        frame=message.bytes();self.sent.append(frame)
        fn,data=frame[5],frame[6:-2]
        if fn==8:self.queue.append(mido.Message('sysex',data=self.ident))
        elif fn==13:self.reply(13,[*p.encode14(self.target),*b'Test'.ljust(32,b'\0')])
        elif fn==12:self.reply(12,[self.scene-1])
        elif fn==14:self.reply(14,[data[0],*bytes(32)])
        elif fn==19:self.reply(19,[v for b in self.blocks for v in (*p.encode14(b.effect_id), b.channels_supported*16+b.channel*2+int(b.bypassed))])
        elif fn==31:
            eid=p.decode14(*data);words=self.words[eid]
            self.reply(0x74,[*p.encode14(eid),*p.encode14(len(words))])
            self.reply(0x75,[0,0,*[v for w in words for v in (w&127,(w>>7)&127,w>>14)]])
            self.reply(0x76,[])
        elif fn==1 and data[:2]==[16,0]:
            pid=p.decode14(*data[4:6]);text=str(self.shown[pid])+(' dB' if pid==21 else '')
            bits=''.join(f'{b:08b}' for b in (text+'\0').encode('ascii'))
            bits+='0'*(-len(bits)%7)
            packed=[int(bits[i:i+7],2) for i in range(0,len(bits),7)]
            self.reply(1,[16,0,58,0,pid,0,*[0]*7,*p.encode14(len(packed)),*packed])
        elif fn==1 and data[:2]==[9,0]:
            if self.fault=='transport':raise OSError('Outcome unknown')
            eid,pid=p.decode14(*data[2:4]),p.decode14(*data[4:6])
            value=p.decode_f32_septets(data[6:11])*10
            self.words[eid][pid]=round(value/10*65534)
            self.shown[pid]=round(value,2)
            if self.fault=='other_word':self.words[62][10]+=1
            if self.fault=='modifier':self.words[3][9]+=1
            if self.fault=='wrong_value':self.shown[pid]=2.
        else:raise AssertionError('Unexpected frame at independent port')
    def writes(self):return [f for f in self.sent if f[5:8]==[1,9,0]]


@pytest.fixture
def rig(monkeypatch):
    monkeypatch.setattr(cal.time,'sleep',lambda _:None)
    port=Port();dev=cal.Device((port,port))
    # Grid semantics are independent scripted data; decoder is covered elsewhere.
    dev.read_grid=lambda:deepcopy(port.cells)
    yield dev,port
    dev.close()


@pytest.mark.parametrize('control,value',list(cal.LITERALS))
def test_each_literal_matches_captured_wire_and_preserves_every_other_word(rig,control,value):
    dev,port=rig
    before=dev.observe()
    review=dev.review(cal.Edit(control,value),external_audio_muted=True)
    assert not port.writes()
    result=dev.apply(review,external_audio_muted=True)
    assert result==dict(verified=True,sent=value!=5.,stored=False)
    assert len(port.writes())==int(value!=5.)
    after=dev.observe();pid=cal.PIDS[control]
    after['bulk']['58'][pid]=before['bulk']['58'][pid]
    after['shown'][control]=before['shown'][control]
    assert after==before and after['modifiers'][0][9]==78
    with pytest.raises(PermissionError):dev.apply(review,external_audio_muted=True)


def test_separate_explicit_reviews_restore_baseline(rig):
    dev,port=rig;before=dev.observe()
    for edit in (cal.Edit('gain',4.6),cal.Edit('mid',5.6),cal.Edit('gain',5.),cal.Edit('mid',5.)):
        assert dev.apply(dev.review(edit,external_audio_muted=True),external_audio_muted=True)['sent']
    assert dev.observe()==before and len(port.writes())==4


@pytest.mark.parametrize('bad',[('gain',True),('gain',0),('gain',8),('mid',4.6),('level',5),('gain',float('nan')),('gain','4.6')])
def test_not_a_generic_parameter_setter(bad):
    with pytest.raises(ValueError):cal.Edit(*bad)


@pytest.mark.parametrize('fault',['identity','target','scene','cable','channel','layout','active_mod','assigned_mod','loud','model','missing_name'])
def test_preflight_refusal_sends_no_parameter_write(rig,fault):
    dev,port=rig
    if fault=='identity':port.ident=fw33_profile.IDENTITY
    if fault=='target':port.target=326
    if fault=='scene':port.scene=2
    if fault=='cable':port.cells[1].cable_in_mask=1
    if fault=='channel':port.blocks[0].channel=1
    if fault=='layout':port.words[58].pop()
    if fault=='active_mod':port.words[3][0]=12
    if fault=='assigned_mod':port.words[3][8]=58
    if fault=='loud':port.shown[21]=0.
    if fault=='model':port.words[58][0]=14
    if fault=='missing_name':dev.scene_name=lambda s:None
    with pytest.raises((PermissionError,ValueError)):dev.review(cal.Edit('gain',4.6),external_audio_muted=True)
    assert not port.writes()


@pytest.mark.parametrize('fault',['transport','other_word','modifier','wrong_value'])
def test_unknown_or_mismatched_write_latches_connection_and_never_retries(rig,fault):
    dev,port=rig
    review=dev.review(cal.Edit('gain',4.6),external_audio_muted=True)
    port.fault=fault
    with pytest.raises((OSError,ValueError)):dev.apply(review,external_audio_muted=True)
    assert dev.uncertain and not dev.active and len(port.writes())==1
    with pytest.raises(PermissionError):dev.review(cal.Edit('gain',5.),external_audio_muted=True)
    assert len(port.writes())==1


@pytest.mark.parametrize('flag',[False,1,'true',None])
def test_exact_mute_acknowledgement_is_required_at_both_boundaries(rig,flag):
    dev,port=rig
    with pytest.raises(PermissionError):dev.review(cal.Edit('gain',4.6),external_audio_muted=flag)
    review=dev.review(cal.Edit('gain',4.6),external_audio_muted=True)
    with pytest.raises(PermissionError):dev.apply(review,external_audio_muted=flag)
    with pytest.raises(PermissionError):dev.apply(review,external_audio_muted=True)
    assert not port.writes()


def test_stale_foreign_expired_or_replaced_review_does_not_write(rig,monkeypatch):
    dev,port=rig
    first=dev.review(cal.Edit('gain',4.6),external_audio_muted=True)
    newer=dev.review(cal.Edit('mid',5.6),external_audio_muted=True)
    for review in (first,replace(newer)):
        with pytest.raises(PermissionError):dev.apply(review,external_audio_muted=True)
    monkeypatch.setattr(cal.time,'monotonic',lambda:newer.expires+1)
    with pytest.raises(PermissionError):dev.apply(newer,external_audio_muted=True)
    assert not port.writes()


def test_unarmed_direct_writes_store_and_foreign_thread_are_refused(rig):
    dev,port=rig;edit=cal.Edit('gain',4.6)
    with pytest.raises(PermissionError):dev._send(edit.frame())
    for frame in (protocol.envelope(12,[0]),protocol.param_frame(58,21,0,opcode=9),protocol.envelope(1,[0x26,0])):
        with pytest.raises(PermissionError):dev._send(frame)
    errors=[];dev.active=True
    def send():
        try:dev._send(edit.frame())
        except PermissionError:errors.append(True)
    with dev.outp.once(edit):
        thread=threading.Thread(target=send);thread.start();thread.join()
    dev.active=False
    assert errors==[True] and not port.writes()


def test_normal_adapter_still_refuses_the_same_new_build_write(rig):
    dev,port=rig
    assert dev.reg.firmware not in SUPPORTED_FIRMWARE
    assert not dev.capabilities().verifies_writes
    with pytest.raises(PermissionError):AxeFxIII._send(dev,cal.Edit('gain',4.6).frame())
    assert not port.writes()
