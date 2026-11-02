"""Official profile and complete preservation, with independent synthetic ports."""
import struct

import mido
import pytest

from devices.axefx3 import protocol as p
from devices.axefx3.amp_writer import AmpEdit, AmpReadbackError, AmpWriter
from devices.axefx3.beta5_amp_writer import Beta5AmpWriter
from devices.axefx3.official_amp_writer import OfficialAmpWriter
from fm9.device import ReadOnly
from tests.test_axefx3_live_observation import ObservationPorts
from tests.test_axefx3_amp_writer import GAIN3_3


OFFICIAL3301 = tuple(bytes.fromhex(
    '00 01 74 10 08 21 01 10 01 11 00 00 4f 63 74 20 33 31 20 32 30 32 36 '
    '20 30 35 3a 35 37 3a 32 32 00 00 00 00 00 00 00 00 00 00 00 00 46'))


class OfficialPorts(ObservationPorts):
    def __init__(self):
        super().__init__()
        self.identity = OFFICIAL3301
        self.words[58] = [0] * 568
        self.words[58][1] = 19660
        self.words[58][3] = 32767
        self.writes, self.behavior = [], 'apply'

    def send(self, message):
        frame = message.bytes()
        if frame[5:8] == [1, 9, 0]:
            self.writes.append(frame)
            if self.behavior == 'raise': raise OSError('May already have been sent')
            if self.behavior == 'ignore': return
            assert frame[8:10] == [58, 0] and frame[10] in (1, 3) and frame[11] == 0
            value = struct.unpack('<f', sum(b << (7*i) for i,b in enumerate(frame[12:17])).to_bytes(4,'little'))[0]
            self.words[58][frame[10]] = round(value * 65534)
            if self.behavior == 'unknown': self.words[206][0] -= 1
            if self.behavior == 'system': self.words[200][0] -= 1
            if self.behavior == 'modifier': self.words[34][24] -= 1
            if self.behavior == 'other_channel': self.words[58][143] += 1
            if self.behavior == 'level': self.words[58][21] += 1
            if self.behavior == 'identity': self.identity = tuple(p.envelope(8,[33,1])[1:-1])
            return
        if frame[5:8] == [1, 16, 0]:
            self.sent.append(frame)
            pid = frame[10]
            text = 'WRONG' if self.behavior == 'bad_display' and self.writes else f'{self.words[58][pid]/65534*10:.2f}'
            bits=''.join(f'{b:08b}' for b in (text+'\0').encode())
            bits=bits.ljust((len(bits)+6)//7*7,'0')
            data=[int(bits[i:i+7],2) for i in range(0,len(bits),7)]
            reply=p.envelope(1,[16,0,58,0,pid,0,*([0]*7),len(data),0,*data])[1:-1]
            self.queue.append(mido.Message('sysex',data=reply))
            return
        super().send(message)


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',lambda *a,**k:pytest.fail('No real MIDI'))
    monkeypatch.setattr('devices.axefx3.amp_writer.time.sleep',lambda _:None)
    ports=OfficialPorts();dev=OfficialAmpWriter((ports.inp,ports.outp))
    yield dev,ports
    dev.close()


def test_official_write_uses_existing_codec_and_preserves_all_opaque_surfaces(device):
    dev,ports=device
    original=dev.capture().data()
    review=dev.review_amp(AmpEdit(323,'gain',3.3))
    assert not ports.writes
    result=dev.apply_amp(review,external_audio_muted=True)
    assert result==dict(verified=True,sent=True,stored=False)
    assert ports.writes==[GAIN3_3]
    after=dev.capture().data();after['bulk']['58'][1]=original['bulk']['58'][1]
    assert after==original
    assert not dev.capabilities().can_verify
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert len(ports.writes)==1


@pytest.mark.parametrize('fault',['unknown','system','modifier','other_channel','level','identity','bad_display','raise','ignore'])
def test_unknown_outcome_consumes_review_and_latches_without_retry(device,fault):
    dev,ports=device
    review=dev.review_amp(AmpEdit(323,'gain',3.3));ports.behavior=fault
    with pytest.raises(AmpReadbackError):dev.apply_amp(review,external_audio_muted=True)
    assert len(ports.writes)==1 and dev._uncertain
    with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(323,'gain',3.3))
    assert len(ports.writes)==1


@pytest.mark.parametrize('fault',['model','channel','short','owner_source_none','changed_context'])
def test_preflight_refuses_unqualified_or_changed_context(device,fault):
    dev,ports=device
    review=dev.review_amp(AmpEdit(323,'gain',3.3))
    if fault=='model':ports.words[58][0]=14
    elif fault=='short':ports.words[58].pop()
    elif fault=='owner_source_none':ports.words[3][8:10]=[58,1]
    elif fault=='changed_context':ports.words[201][1]-=1
    elif fault=='channel':
        old=ports.answer
        def answer(frame):
            result=old(frame)
            if frame[5]==19:
                args=result[0][5:-1];args[2]=66
                return [p.envelope(19,args)[1:-1]]
            return result
        ports.answer=answer
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert not ports.writes


@pytest.mark.parametrize('writer',[AmpWriter,Beta5AmpWriter])
def test_official_identity_does_not_promote_older_writers(writer):
    ports=OfficialPorts();dev=writer((ports.inp,ports.outp))
    try:
        with pytest.raises(ReadOnly):dev.review_amp(AmpEdit(323,'gain',3.3))
        assert not ports.writes
    finally:dev.close()


def test_unrelated_custom_modifiers_are_preserved_but_not_edited(device):
    dev,ports=device
    ports.words[34][0]=13;ports.words[34][8:10]=[70,2]
    before=dev.capture().data()
    review=dev.review_amp(AmpEdit(323,'mid',5.6))
    assert dev.apply_amp(review,external_audio_muted=True)['verified']
    assert dev.capture().data()['modifiers']==before['modifiers']


@pytest.mark.parametrize('chassis',['mk1','turbo','unknown'])
def test_other_chassis_refused_before_port_open(chassis):
    with pytest.raises(ReadOnly):OfficialAmpWriter(chassis=chassis)


def test_mute_and_current_single_use_review_are_required(device):
    dev,ports=device
    review=dev.review_amp(AmpEdit(323,'gain',3.3))
    with pytest.raises(ReadOnly):dev.apply_amp(review)
    replacement=dev.review_amp(AmpEdit(323,'mid',5.6))
    with pytest.raises(ReadOnly):dev.apply_amp(review,external_audio_muted=True)
    assert not ports.writes
    assert dev.apply_amp(replacement,external_audio_muted=True)['verified']
