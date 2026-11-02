"""Independent synthetic receive packets; never hardware queries."""
from dataclasses import FrozenInstanceError

import pytest

from devices.axefx3 import protocol
from devices.axefx3.observed_words import Broadcast, assemble


def burst(eid=58, words=(0, 65535, 16383, 65534), chunk=2):
    def packet(fn, data): return protocol.envelope(fn, data)[1:-1]
    result = [packet(116, [eid & 127, eid >> 7, len(words) & 127, len(words) >> 7])]
    for start in range(0, len(words), chunk):
        body = [v for w in words[start:start + chunk] for v in (w & 127, w >> 7 & 127, w >> 14)]
        size = len(body) // 3
        result.append(packet(117, [size & 127, size >> 7, *body]))
    return [*result, packet(118, [])]


def test_receive_words_preserves_uint16_sentinels_and_has_no_output():
    result = assemble(iter(burst()), 58)
    assert result == Broadcast(58, 4, (0, 65535, 16383, 65534))
    assert '65535' not in repr(result)
    with pytest.raises(FrozenInstanceError): result.count = 1


@pytest.mark.parametrize('fault', ['no_head', 'double_head', 'no_body', 'no_end',
    'short_count', 'long_count', 'wrong_id', 'bad_checksum', 'bad_product',
    'bad_top_bits', 'short_body', 'reserved', 'unrelated', 'trailing', 'empty',
    'zero_count', 'long_header', 'long_end', 'f0f7', 'boolean', 'oversized'])
def test_incomplete_or_unobserved_bursts_never_return_partial_words(fault):
    data = burst()
    if fault == 'no_head': data.pop(0)
    elif fault == 'double_head': data.insert(1, data[0])
    elif fault == 'no_body': data.pop(1)
    elif fault == 'no_end': data.pop()
    elif fault in ('short_count', 'long_count'):
        data[0] = protocol.envelope(116, [58, 0, 3 if fault == 'short_count' else 5, 0])[1:-1]
    elif fault == 'wrong_id': data = burst(62)
    elif fault == 'bad_checksum': data[1][-1] ^= 1
    elif fault == 'bad_product': data[1] = [0, 1, 116, 17, *data[1][4:]]
    elif fault == 'bad_top_bits': data[1] = protocol.envelope(117, [0, 0, 0, 0, 4])[1:-1]
    elif fault == 'short_body': data[1] = protocol.envelope(117, [0, 0, 1])[1:-1]
    elif fault == 'reserved': data[1] = protocol.envelope(117, [1, 0, 0, 0, 0])[1:-1]
    elif fault == 'unrelated': data[1] = protocol.envelope(8, [33, 1])[1:-1]
    elif fault == 'trailing': data.append(data[-1])
    elif fault == 'empty': data = []
    elif fault == 'zero_count': data = [protocol.envelope(116, [58, 0, 0, 0])[1:-1], data[-1]]
    elif fault == 'long_header': data[0] = protocol.envelope(116, [58, 0, 4, 0, 0])[1:-1]
    elif fault == 'long_end': data[-1] = protocol.envelope(118, [0])[1:-1]
    elif fault == 'f0f7': data[0] = [240, *data[0], 247]
    elif fault == 'boolean': data[0][0] = False
    elif fault == 'oversized': data[1] = [0] * 4097
    with pytest.raises(ValueError): assemble(data, 58)


@pytest.mark.parametrize('eid', [True, -1, 0, 208, '58', 58.])
def test_explicit_valid_block_id_required(eid):
    with pytest.raises(ValueError): assemble(burst(), eid)


@pytest.mark.parametrize('args', [(58, 1, (True,)), (58, 1, (-1,)), (58, 1, (65536,)),
    (58, True, (1,)), (True, 1, (1,)), (58, 2, (1,)), (58, 1, [1]), (58, 0, ())])
def test_structural_record_cannot_guess_or_mask_words(args):
    with pytest.raises(ValueError): Broadcast(*args)


def test_excessive_fragment_count_is_bounded():
    data = burst(words=(0,) * 1023, chunk=1)
    with pytest.raises(ValueError, match='excessive'): assemble(data, 58)


@pytest.mark.parametrize('packets', [None, 3, True])
def test_non_iterable_input_is_not_a_default_empty_broadcast(packets):
    with pytest.raises(ValueError, match='iterable'): assemble(packets, 58)


@pytest.mark.parametrize('size', [25, 28, 40, 56, 94, 100, 104, 128, 132, 140,
                                    148, 168, 176, 245, 256])
def test_measured_nonzero_chunk_word_counts_are_not_reserved_fields(size):
    packets = burst(58, (65535,) * size, chunk=256)
    assert packets[1][5:7] == [size & 127, size >> 7]
    assert assemble(packets, 58).words == (65535,) * size


def test_complete_amp_broadcast_is_256_256_56_words():
    packets = burst(58, (7,) * 568, chunk=256)
    assert [p[5:7] for p in packets[1:-1]] == [[0, 2], [0, 2], [56, 0]]
    assert assemble(packets, 58).count == 568


@pytest.mark.parametrize('count', [0, 1, 3, 257])
def test_zero_or_mismatched_chunk_count_does_not_bypass_total_count(count):
    packets = burst(58, (7, 8))
    packets[1] = protocol.envelope(117, [count & 127, count >> 7, 7, 0, 0, 8, 0, 0])[1:-1]
    with pytest.raises(ValueError): assemble(packets, 58)


def test_chunk_over_measured_256_word_bound_is_refused_even_if_counts_match():
    with pytest.raises(ValueError): assemble(burst(58, (1,) * 257, chunk=257), 58)
