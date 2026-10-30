"""Exact read-only build recognition, not new firmware-write acceptance."""
import hashlib

import mido
import pytest

from devices.axefx3 import firmware_identity, fw33_profile, profile, protocol
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.registry import Registry, SUPPORTED_FIRMWARE
from fm9 import protocol as shared


BETA5 = tuple(bytes.fromhex(
    '00 01 74 10 08 61 00 10 01 11 00 00 4f 63 74 20 32 36 20 32 30 32 36 '
    '20 31 32 3a 34 32 3a 34 35 00 00 00 00 00 00 00 00 00 00 00 00 02'))


def test_exact_observed_build_is_named_but_not_a_writable_profile():
    assert protocol.valid_reply(list(BETA5))
    assert hashlib.sha256(bytes(BETA5)).hexdigest() == firmware_identity.BETA5_IDENTITY_SHA256
    assert firmware_identity.identify(BETA5) == firmware_identity.BETA5_KEY
    assert firmware_identity.identify(list(BETA5)) == firmware_identity.BETA5_KEY
    assert fw33_profile.identity_key(BETA5) is None
    assert firmware_identity.BETA5_KEY not in SUPPORTED_FIRMWARE
    reg = Registry(firmware_identity.BETA5_KEY)
    assert reg.params == {} and reg.selectable_amp_models() == {}
    for variant in ('mk1', 'mk2'):
        policy = profile.memory_policy(reg.firmware, variant)
        assert not policy['write_supported'] and not policy['nam_writes']
    assert not profile.memory_policy(reg.firmware, 'mk1')['user2_cabs']
    assert profile.memory_policy(reg.firmware, 'mk2')['user2_cabs']


def test_previous_profile_and_its_definitions_are_retained():
    assert firmware_identity.identify(fw33_profile.IDENTITY) == fw33_profile.KEY
    assert fw33_profile.identity_key(fw33_profile.IDENTITY) == fw33_profile.KEY
    assert fw33_profile.KEY in SUPPORTED_FIRMWARE and '32.06' in SUPPORTED_FIRMWARE
    assert len(Registry(fw33_profile.KEY).params) == 83


@pytest.mark.parametrize('position', range(len(BETA5)))
def test_each_changed_byte_is_unknown_even_with_a_valid_checksum(position):
    altered = list(BETA5)
    altered[position] ^= 1
    assert firmware_identity.identify(altered) is None
    if position != len(BETA5) - 1:
        altered[-1] = shared.checksum(altered[:-1])
        assert firmware_identity.identify(altered) is None


@pytest.mark.parametrize('reply', [None, [], (), b'33.00', '33.00', [97, 0],
    list(BETA5) + [0], list(BETA5[:-1]), [True, *BETA5[1:]],
    [0., *BETA5[1:]], [-1, *BETA5[1:]], [128, *BETA5[1:]]])
def test_malformed_or_generic_labels_do_not_identify_a_build(reply):
    assert firmware_identity.identify(reply) is None


class IdentityPorts:
    def __init__(self, reply):
        self.reply, self.queue, self.sent = reply, [], []
    def iter_pending(self):
        while self.queue:
            yield self.queue.pop(0)
    def send(self, message):
        frame = message.bytes()
        self.sent.append(frame)
        if frame == protocol.envelope(8, []):
            self.queue.append(mido.Message('sysex', data=self.reply))
        elif frame == protocol.envelope(13, [127,127]):
            self.queue.append(mido.Message('sysex', data=protocol.envelope(13,
                [*shared.encode14(327), *b'<EMPTY>'.ljust(32,b'\0')])[1:-1]))
        else:
            raise AssertionError('No operation beyond identity/current-name reads expected')
    def close(self):
        pass


def test_identity_query_ignores_captured_cursor_echo_without_resending_the_command():
    class EchoPorts(IdentityPorts):
        def send(self,message):
            if message.bytes()==protocol.envelope(8,[]):
                self.queue.append(mido.Message('sysex',data=bytes.fromhex(
                    'f0 00 01 74 10 01 30 00 00 00 00 00 06 00 00 00 00 00 00 00 00 22 f7')[1:-1]))
            super().send(message)
    ports=EchoPorts(BETA5);dev=AxeFxIII((ports,ports))
    try:
        before=len(ports.sent)
        assert dev._request(protocol.envelope(8,[]),firmware_identity.parse_response)==BETA5
        assert ports.sent[before:]==[protocol.envelope(8,[])]
    finally:dev.close()


@pytest.mark.parametrize('reply',[None,[],[0],list(BETA5[:-1]),
    [*BETA5[:-1],BETA5[-1]^1],protocol.envelope(13,[0,0])[1:-1]])
def test_identity_parser_refuses_malformed_and_unrelated_replies(reply):
    assert firmware_identity.parse_response(reply) is None


def test_identity_parser_does_not_hide_an_unknown_firmware_response():
    unknown=protocol.envelope(8,[32,6])[1:-1]
    assert firmware_identity.parse_response(unknown)==tuple(unknown)
    assert firmware_identity.identify(unknown) is None


@pytest.mark.parametrize('reply, expected', [
    (BETA5, firmware_identity.BETA5_KEY),
    (fw33_profile.IDENTITY, fw33_profile.KEY),
    (tuple(protocol.envelope(8,[97,0])[1:-1]), '97.00'),
    (tuple(protocol.envelope(8,[32,6])[1:-1]), '32.06')])
def test_adapter_read_only_connect_does_not_send_a_set(reply, expected):
    ports = IdentityPorts(reply)
    dev = AxeFxIII((ports,ports))
    try:
        assert dev.firmware_label() == expected and dev.reg.firmware == expected
        if expected in (firmware_identity.BETA5_KEY, '97.00'):
            assert not dev.capabilities().verifies_writes
            assert not dev.capabilities().can_rename
            with pytest.raises((ValueError,PermissionError)):
                with dev.edit_session(external_audio_muted=True,expected_preset=327):
                    raise AssertionError('Unverified Beta 5 must not enter an edit session')
        assert all(frame in (protocol.envelope(8,[]),protocol.envelope(13,[127,127])) for frame in ports.sent)
    finally:
        dev.close()
