"""Display recognition is deliberately independent of writer acceptance."""
import hashlib

import pytest

from devices.axefx3 import observed_firmware as identity, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.amp_writer import AmpEdit, AmpWriter
from devices.axefx3.beta5_amp_writer import Beta5AmpWriter
from fm9 import protocol as shared
from fm9.device import ReadOnly
from tests.axefx3_beta5_identity import BETA5
from tests.axefx3_official_identity import RELEASE3300, RELEASE3301
from tests.test_axefx3_amp_writer import AmpPorts


BUILDS = [(BETA5, '33.00-beta5.20261026'),
          (RELEASE3300, '33.00.20261030'), (RELEASE3301, '33.01.20261031')]


@pytest.fixture(autouse=True)
def no_physical_ports(monkeypatch):
    monkeypatch.setattr('fm9.midi_transport.open_ports',
                        lambda *a, **k: pytest.fail('Physical MIDI forbidden'))


@pytest.mark.parametrize('reply,label', BUILDS)
def test_captured_reply_is_named_without_granting_capabilities(reply, label):
    assert identity.OBSERVED_BUILDS[hashlib.sha256(bytes(reply)).hexdigest()] == label
    assert identity.observed_build(reply) == identity.observed_build(list(reply)) == label
    ports = AmpPorts()
    ports.identity = reply
    dev = AxeFxIII((ports.inp, ports.outp))
    try:
        assert dev.firmware_label() == label
        assert not dev.capabilities().verifies_writes and not dev.capabilities().can_rename
        assert not ports.writes
        assert all(protocol.allowed(frame, 'mk1') for frame in ports.sent)
    finally:
        dev.close()


@pytest.mark.parametrize('reply,label', BUILDS)
@pytest.mark.parametrize('position', range(len(RELEASE3301)))
def test_every_changed_byte_is_unknown_even_with_a_repaired_checksum(reply, label, position):
    altered = list(reply)
    altered[position] ^= 1
    if position != len(altered) - 1:
        altered[-1] = shared.checksum(altered[:-1])
    assert identity.observed_build(altered) is None


@pytest.mark.parametrize('reply', [None, [], (), b'33.01', '33.01', [33, 1],
    list(RELEASE3301[:-1]), [True, *RELEASE3301[1:]],
    [0., *RELEASE3301[1:]], [-1, *RELEASE3301[1:]], [128, *RELEASE3301[1:]],
    protocol.envelope(13, [33, 1])[1:-1]])
def test_malformed_and_unrelated_replies_have_no_label(reply):
    assert identity.parse_reply(reply) is None
    assert identity.observed_build(reply) is None
    assert identity.display_label(reply) == ''


@pytest.mark.parametrize('major,minor', [(32, 6), (33, 0), (33, 1), (97, 0)])
def test_unknown_valid_build_keeps_raw_version_not_a_beta_alias(major, minor):
    reply = protocol.envelope(8, [major, minor])[1:-1]
    assert identity.parse_reply(reply) == tuple(reply)
    assert identity.observed_build(reply) is None
    assert identity.display_label(reply) == f'{major}.{minor:02d}'


def test_extended_packet_is_unknown_not_the_captured_official_build():
    reply = [*RELEASE3301, 0]  # Still a valid XOR checksum, but a different packet.
    assert identity.parse_reply(reply) == tuple(reply)
    assert identity.observed_build(reply) is None
    assert identity.display_label(reply) == '33.01'


@pytest.mark.parametrize('writer', [AmpWriter, Beta5AmpWriter])
@pytest.mark.parametrize('reply', [RELEASE3300, RELEASE3301])
def test_official_labels_never_promote_either_existing_writer(writer, reply):
    ports = AmpPorts()
    ports.identity, ports.amp[0] = reply, 0
    dev = writer((ports.inp, ports.outp))
    try:
        with pytest.raises(ReadOnly):
            dev.review_amp(AmpEdit(320, 'gain', 3.3))
        assert not ports.writes
    finally:
        dev.close()
