"""Synthetic 33.02 writer regression, native qualification remains separate."""
import mido
import pytest

from devices.axefx3.release3302_amp_writer import Release3302AmpWriter
from devices.axefx3.amp_writer import AmpEdit, AmpReadbackError
from devices.axefx3 import protocol as wire
from fm9.device import ReadOnly
from tests.axefx3_3302_identity import RELEASE3302
from tests.test_axefx3_official_amp_writer import OfficialPorts, OFFICIAL3301


@pytest.fixture
def device(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports', lambda *a, **k: pytest.fail('No physical MIDI'))
    ports = OfficialPorts()
    ports.identity, ports.preset = RELEASE3302, 329
    dev = Release3302AmpWriter((ports.inp, ports.outp))
    yield dev, ports
    dev.close()


@pytest.mark.parametrize('control,value', [('gain', 3.3), ('mid', 5.6)])
def test_exact_reviewed_change_reuses_complete_preservation_and_no_store(device, control, value):
    dev, ports = device
    before = dev.capture().data()
    review = dev.review_amp(AmpEdit(329, control, value))
    result = dev.apply_amp(review, external_audio_muted=True)
    assert result['stored'] is False and len(ports.writes) == 1
    after = dev.capture().data()
    assert abs(after['bulk']['58'][review.edit.pid] / 65534 * 10 - value) < .011
    after['bulk']['58'][review.edit.pid] = before['bulk']['58'][review.edit.pid]
    assert after == before
    assert not dev.capabilities().verifies_writes
    with pytest.raises(ReadOnly): dev.apply_amp(review, external_audio_muted=True)
    assert len(ports.writes) == 1


@pytest.mark.parametrize('reply', [OFFICIAL3301, tuple(wire.envelope(8, [33, 2])[1:-1])])
def test_other_firmware_never_inherits_the_new_writer(device, reply):
    dev, ports = device
    ports.identity = reply
    with pytest.raises(ReadOnly): dev.review_amp(AmpEdit(329, 'gain', 3.3))
    assert not ports.writes


@pytest.mark.parametrize('behavior', ['raise', 'ignore', 'unknown', 'system', 'modifier',
    'other_channel', 'level', 'identity', 'bad_display'])
def test_uncertainty_is_terminal_and_preserves_one_attempt_limit(device, behavior):
    dev, ports = device
    review = dev.review_amp(AmpEdit(329, 'gain', 3.3))
    ports.behavior = behavior
    with pytest.raises(AmpReadbackError):
        dev.apply_amp(review, external_audio_muted=True)
    assert len(ports.writes) == 1 and dev._uncertain
    with pytest.raises(ReadOnly): dev.review_amp(AmpEdit(329, 'gain', 3.3))
    assert len(ports.writes) == 1


def test_final_output_still_refuses_unreviewed_or_different_mutation(device):
    dev, ports = device
    for frame in (AmpEdit(329, 'gain', 3.3).frame(), wire.envelope(1, [9, 0, 58, 0, 21, 0] + [0] * 9),
            wire.envelope(1, [0x52, 0] + [0] * 13)):
        with pytest.raises(ReadOnly): dev.outp.send(mido.Message('sysex', data=frame[1:-1]))
    assert not ports.writes
