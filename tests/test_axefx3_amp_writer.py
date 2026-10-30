"""Independent fake wire replies, not physical MK2 or audio acceptance."""
from dataclasses import replace
import ast
import json
from pathlib import Path
import struct
import threading

import mido
import pytest

from devices.axefx3 import readonly_protocol as p
from devices.axefx3.readonly_adapter import AxeFxIII, ReadOnlyOutput
from devices.axefx3.amp_writer import AmpEdit, AmpWriter, AmpReadbackError, _AmpOutput
from devices.axefx3.beta5_amp_writer import Beta5AmpWriter
from tests.test_axefx3_firmware_identity import BETA5
from devices.axefx3.name_writer import MK2_FW33_IDENTITY
from fm9.device import ReadOnly
from fm9.safety import BrickGuardRefusal
from tests.test_axefx3_readonly import FakePorts


GAIN4 = [240,0,1,116,16,1,9,0,58,0,1,0,77,25,51,118,3,0,0,0,0,52,247]
MID6 = [240,0,1,116,16,1,9,0,58,0,3,0,26,51,102,120,3,0,0,0,0,16,247]
# 3.3 is rounded to float32 BEFORE the division by ten (FW33). Without that
# step the first value byte would be 67, not 66; 4.0 and 6.0 cannot tell.
GAIN3_3 = [240,0,1,116,16,1,9,0,58,0,1,0,66,107,35,117,3,0,0,0,0,90,247]


class AmpPorts(FakePorts):
    def __init__(self):
        super().__init__()
        self.writes, self.types = [], []
        self.identity, self.behavior = MK2_FW33_IDENTITY, 'apply'
        self.amp = [0] * 568
        for base in range(0,568,142):
            self.amp[base]=14
            self.amp[base+1]=19660
            self.amp[base+3]=32767
        self.mods = {eid:[0]*25 for eid in range(3,35)}
        self.channel, self.missing_amp, self.bad_bulk = 0, False, ''

    def send(self, message):
        wire = message.bytes()  # Real serialization boundary, independent decoder.
        self.types.append(type(message))
        self.sent.append(wire)
        if wire[5:8] == [1,9,0]:
            self.writes.append(wire)
            if self.behavior == 'raise':raise OSError('Transport may already have sent it')
            if self.behavior == 'ignore':return
            assert wire[8:10] == [58,0] and wire[10] in (1,3) and wire[11]==0
            raw=sum(n << (7*i) for i,n in enumerate(wire[12:17]))
            value=struct.unpack('<f',raw.to_bytes(4,'little'))[0]
            self.amp[wire[10]]=round(value*65534)
            if self.behavior == 'other_channel':self.amp[142+1]+=1
            if self.behavior == 'level':self.amp[21]+=1
            if self.behavior == 'modifier':self.mods[3][4]=1
            if self.behavior == 'scene':self.scene=1
            if self.behavior == 'preset':self.preset=321
            if self.behavior == 'identity':self.identity=tuple(p.envelope(8,[33,0])[1:-1])
            return
        for data in self.answer(wire):self.queue.append(mido.Message('sysex',data=data))

    def answer(self, wire):
        fn,args=wire[5],wire[6:-2]
        if fn==8:return [list(self.identity)]
        if fn==19:
            return [p.envelope(19,([] if self.missing_amp else [58,0,64+self.channel])+[62,0,64])[1:-1]]
        if fn==31:
            eid=args[0];words=list(self.amp if eid==58 else self.mods[eid])
            head=[eid,0,len(words)&127,len(words)>>7]
            if self.bad_bulk=='count':head[2]-=1
            result=[p.envelope(116,head)[1:-1]]
            for offset in range(0,len(words),64):
                body=[]
                for word in words[offset:offset+64]:body.extend([word&127,(word>>7)&127,word>>14])
                result.append(p.envelope(117,[0,0,*body])[1:-1])
            if self.bad_bulk=='body':result[-1]=p.envelope(117,[0,0,1])[1:-1]
            if self.bad_bulk=='missing':result.pop()
            result.append(p.envelope(118,[])[1:-1])
            return result
        if fn==1 and args[:2]==[16,0]:
            pid=args[4];text=f'{self.amp[pid]/65534*10:.2f}'
            if self.behavior=='bad_display' or self.behavior=='bad_display_after' and self.writes:text='6 dB'
            bits=''.join(f'{b:08b}' for b in (text+'\0').encode('ascii'))
            bits=bits.ljust((len(bits)+6)//7*7,'0')
            payload=[int(bits[i:i+7],2) for i in range(0,len(bits),7)]
            return [p.envelope(1,[16,0,58,0,pid,0,*([0]*7),len(payload),0,*payload])[1:-1]]
        return super().answer(wire)


@pytest.fixture(params=[AmpWriter, Beta5AmpWriter])
def writer(monkeypatch, request):
    ports=AmpPorts()
    if request.param is Beta5AmpWriter:
        ports.identity=BETA5
        ports.amp[0]=0
    dev=request.param((ports.inp,ports.outp))
    monkeypatch.setattr('devices.axefx3.amp_writer.time.sleep',lambda _:None)
    yield dev,ports
    dev.close()


@pytest.mark.parametrize('control,value,wire',[('gain',4,GAIN4),('mid',6,MID6),('gain',3.3,GAIN3_3)])
def test_literal_port_bytes_single_use_and_preserved_context(writer,control,value,wire):
    dev,ports=writer;before=list(ports.amp)
    edit=AmpEdit(320,control,value);review=dev.review_amp(edit)
    assert not ports.writes and review.preview()['executable']
    assert dev.apply_amp(review,external_audio_muted=True)==dict(verified=True,sent=True,stored=False)
    assert ports.writes==[wire] and set(ports.types)=={mido.Message}
    after=list(ports.amp);after[edit.pid]=before[edit.pid]
    assert after==before
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert len(ports.writes)==1
    assert not dev.capabilities().verifies_writes and not dev.capabilities().stores_presets


@pytest.mark.parametrize('args',[(True,'gain',4),(-1,'gain',4),(1024,'gain',4),
    (320,'level',4),(320,'Gain',4),(320,'mid',0),(320,'gain',9),(320,'gain',4.01),
    (320,'gain',True),(320,'mid',float('nan')),(320,'mid',float('inf'))])
def test_invalid_proposals_are_not_clamped(args):
    with pytest.raises(ValueError):AmpEdit(*args)


@pytest.mark.parametrize('consent',[False,None,1,'yes',[],{}])
def test_external_mute_is_explicit_not_truthiness(writer,consent):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4))
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=consent)
    assert not ports.writes


def test_current_value_noop_sends_no_set_and_consumes_review(writer):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',3))
    assert dev.apply_amp(review,external_audio_muted=True)==dict(verified=True,sent=False,stored=False)
    assert not ports.writes
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)


def test_step_limit_target_foreign_review_and_replacement(writer):
    dev,ports=writer
    for edit in (AmpEdit(321,'gain',4),AmpEdit(320,'gain',6)):
        with pytest.raises(ValueError):dev.review_amp(edit)
    first=dev.review_amp(AmpEdit(320,'gain',4))
    for foreign in (None,{},replace(first)):
        with pytest.raises(ReadOnly):dev.apply_amp(foreign,external_audio_muted=True)
    second=dev.review_amp(AmpEdit(320,'mid',6))
    with pytest.raises(ReadOnly):dev.apply_amp(first,external_audio_muted=True)
    dev.apply_amp(second,external_audio_muted=True)
    assert ports.writes==[MID6]


@pytest.mark.parametrize('change',['preset','scene','channel','words','modifier','identity'])
def test_changed_review_context_never_sends(writer,change):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4))
    if change=='preset':ports.preset=321
    if change=='scene':ports.scene=1
    if change=='channel':ports.channel=1
    if change=='words':ports.amp[3]+=1
    if change=='modifier':ports.mods[3][4]=1
    if change=='identity':ports.identity=tuple(p.envelope(8,[97,0])[1:-1])
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert not ports.writes


@pytest.mark.parametrize('failure',['missing_amp','channel','active_modifier','assigned_modifier','bad_display',
    'count','body','missing'])
def test_incomplete_or_unverified_parameter_surface_refuses_review(writer,failure):
    dev,ports=writer
    if failure=='missing_amp':ports.missing_amp=True
    elif failure=='channel':ports.channel=2
    elif failure=='active_modifier':ports.mods[3][0]=12
    elif failure=='assigned_modifier':ports.mods[3][8:10]=[58,1]
    elif failure=='bad_display':ports.behavior='bad_display'
    else:ports.bad_bulk=failure
    with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(320,'gain',4))
    assert not ports.writes


@pytest.mark.parametrize('slot,pid', [(3,5),(4,40),(5,78),(6,39),(7,45),(8,54),(34,65534)])
def test_unused_modifier_residual_parameter_is_preserved(writer,slot,pid):
    dev,ports=writer
    ports.mods[slot][9]=pid
    before={eid:list(words) for eid,words in ports.mods.items()}
    review=dev.review_amp(AmpEdit(320,'gain',3.3))
    assert dev.apply_amp(review,external_audio_muted=True)['verified']
    assert ports.mods==before and ports.writes==[GAIN3_3]


@pytest.mark.parametrize('source,effect,pid',[(12,0,5),(0,58,0),(0,94,5),(12,58,1)])
def test_unused_metadata_does_not_admit_active_or_assigned_modifier(writer,source,effect,pid):
    dev,ports=writer
    ports.mods[3][0]=source
    ports.mods[3][8:10]=[effect,pid]
    with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(320,'gain',3.3))
    assert not ports.writes


@pytest.mark.parametrize('field,value',[(0,12),(8,58),(9,40),(4,123)])
def test_unused_modifier_drift_between_review_and_apply_is_refused(writer,field,value):
    dev,ports=writer
    ports.mods[3][9]=5
    review=dev.review_amp(AmpEdit(320,'gain',3.3))
    ports.mods[3][field]=value
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert not ports.writes


def test_unused_modifier_parameter_drift_after_send_is_uncertain(writer,monkeypatch):
    dev,ports=writer
    ports.mods[3][9]=5
    review=dev.review_amp(AmpEdit(320,'gain',3.3))
    send=ports.outp.send
    def changed(message):
        send(message)
        if message.bytes()[5:8]==[1,9,0]:ports.mods[3][9]=40
    monkeypatch.setattr(ports.outp,'send',changed)
    with pytest.raises(AmpReadbackError):dev.apply_amp(review,external_audio_muted=True)
    assert dev._uncertain and ports.writes==[GAIN3_3]


@pytest.mark.parametrize('behavior',['raise','ignore','other_channel','level','modifier','scene','preset','identity','bad_display_after'])
def test_every_post_send_failure_is_uncertain_without_retry_or_restore(writer,behavior):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4));ports.behavior=behavior
    with pytest.raises(AmpReadbackError):dev.apply_amp(review,external_audio_muted=True)
    assert dev._uncertain and len(ports.writes)==1
    with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(320,'gain',4))
    assert len(ports.writes)==1


def test_deadline_is_checked_after_slow_preflight(writer,monkeypatch):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4))
    real=dev._observe;clock=[review._expires-1]
    monkeypatch.setattr('devices.axefx3.amp_writer.time.monotonic',lambda:clock[0])
    def slow(edit):
        before=real(edit);clock[0]=review._expires;return before
    monkeypatch.setattr(dev,'_observe',slow)
    with pytest.raises(ReadOnly,match='expired'):dev.apply_amp(review,external_audio_muted=True)
    assert not ports.writes and dev.outp._permit is None


@pytest.mark.parametrize('identity', [tuple(p.envelope(8,[97,0])[1:-1]),
    tuple(p.envelope(8,[33,0])[1:-1]), tuple(p.envelope(8,[97,0,16,1,18])[1:-1])])
def test_raw_version_or_other_build_is_not_parameter_firmware_acceptance(writer,identity):
    dev,ports=writer;ports.identity=identity;ports.sent.clear()
    with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(320,'gain',4))
    assert not ports.writes and not any(f[5]==31 for f in ports.sent)


def test_read_settling_does_not_repeat_the_write(writer,monkeypatch):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4))
    real=dev._observe;before=real(review.edit);reads=[]
    def delayed(edit):
        if ports.writes and not reads:
            reads.append(True);return before
        return real(edit)
    monkeypatch.setattr(dev,'_observe',delayed)
    assert dev.apply_amp(review,external_audio_muted=True)['verified']
    assert reads==[True] and ports.writes==[GAIN4]


def test_changed_display_or_bulk_never_invents_independent_success(writer,monkeypatch):
    dev,ports=writer;review=dev.review_amp(AmpEdit(320,'gain',4))
    real=dev._observe
    def inconsistent(edit):
        value=real(edit)
        if ports.writes:value['shown']=3.0
        return value
    monkeypatch.setattr(dev,'_observe',inconsistent)
    with pytest.raises(AmpReadbackError):dev.apply_amp(review,external_audio_muted=True)
    assert len(ports.writes)==1 and dev._uncertain


@pytest.mark.parametrize('chassis',['mk1','turbo',None,'',True])
def test_non_mk2_declines_before_opening_ports(monkeypatch,chassis):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *_:pytest.fail('Physical MIDI opened'))
    with pytest.raises(ReadOnly):AmpWriter(chassis=chassis)


def test_checked_bytes_not_caller_serialization_or_mutation():
    class Hostile(mido.Message):
        def bytes(self):return [0xc0,7]
    original=Hostile('sysex',data=GAIN4[1:-1]);received=[]
    def send(message):
        original.data=tuple(MID6[1:-1]);received.append(message.bytes())
    from types import SimpleNamespace
    output=_AmpOutput(SimpleNamespace(send=send), 'mk2')
    with output._once(AmpEdit(320,'gain',4)):output.send(original)
    assert received==[GAIN4]


def test_final_boundary_refuses_direct_different_foreign_and_cross_thread_writes():
    from types import SimpleNamespace
    received=[];output=_AmpOutput(SimpleNamespace(send=lambda m:received.append(m.bytes())), 'mk2')
    for frame in (GAIN4,MID6,p.envelope(3,[]),p.envelope(31,[59,0]),p.envelope(1,[16,0,58,0,0,0])):
        with pytest.raises(ReadOnly):output.send(mido.Message('sysex',data=frame[1:-1]))
    failures=[]
    with output._once(AmpEdit(320,'gain',4)):
        def other():
            try:output.send(mido.Message('sysex',data=GAIN4[1:-1]))
            except ReadOnly:failures.append(True)
        thread=threading.Thread(target=other);thread.start();thread.join()
        with pytest.raises(ReadOnly):output.send(mido.Message('sysex',data=MID6[1:-1]))
        output.send(mido.Message('sysex',data=GAIN4[1:-1]))
        with pytest.raises(ReadOnly):output.send(mido.Message('sysex',data=GAIN4[1:-1]))
    assert failures==[True] and received==[GAIN4]


def test_normal_readonly_output_and_registry_stay_readonly():
    from types import SimpleNamespace
    raw=SimpleNamespace(send=lambda _:pytest.fail('SET reached ordinary output'))
    for frame in (GAIN4,p.envelope(31,[58,0]),p.envelope(1,[16,0,58,0,1,0])):
        with pytest.raises((ReadOnly,BrickGuardRefusal)):ReadOnlyOutput(raw,'mk2').send(mido.Message('sysex',data=frame[1:-1]))


def test_uncertainty_handler_is_recorded_in_the_component_audit():
    root=Path(__file__).resolve().parents[1]
    audit=json.loads((root/'tests/data/broad_except_audit.json').read_text(encoding='utf-8'))
    records=[r for r in audit['component_blocks'] if r['file']=='devices/axefx3/amp_writer.py']
    tree=ast.parse((root/'devices/axefx3/amp_writer.py').read_text(encoding='utf-8'))
    broad=[n for n in ast.walk(tree) if isinstance(n,ast.ExceptHandler)
           and isinstance(n.type,ast.Name) and n.type.id=='Exception']
    assert len(broad)==len(records)==1 and records[0]['function']=='AmpWriter.apply_amp'


def _silence_scene(monkeypatch, dev, number, after_write=None):
    real = dev.scene_name
    def scene_name(scene=None):
        if scene == number and (after_write is None or after_write()):
            return None
        return real(scene)
    monkeypatch.setattr(dev, 'scene_name', scene_name)


def test_an_unread_scene_name_refuses_the_review(writer, monkeypatch):
    """Unread on both sides used to compare equal and pass verification."""
    dev, ports = writer
    _silence_scene(monkeypatch, dev, 5)
    with pytest.raises(ReadOnly, match='All eight scene names'):
        dev.review_amp(AmpEdit(320, 'gain', 4))
    assert not ports.writes


def test_a_scene_name_lost_after_the_write_is_uncertain(writer, monkeypatch):
    dev, ports = writer
    review = dev.review_amp(AmpEdit(320, 'gain', 4))
    _silence_scene(monkeypatch, dev, 5, after_write=lambda: bool(ports.writes))
    with pytest.raises(AmpReadbackError):
        dev.apply_amp(review, external_audio_muted=True)
    assert ports.writes == [GAIN4]
    with pytest.raises(ReadOnly):
        dev.review_amp(AmpEdit(320, 'gain', 4))
