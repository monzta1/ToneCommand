"""Receive-only block broadcast assembly, never a query or output permit."""
from dataclasses import dataclass, field

from fm9 import protocol as shared
from . import protocol


@dataclass(frozen=True)
class Broadcast:
    effect_id: int
    count: int
    words: tuple[int, ...] = field(repr=False)

    def __post_init__(self):
        if (type(self.effect_id) is not int or not 1 <= self.effect_id <= 207
                or type(self.count) is not int or not 1 <= self.count <= 16383
                or type(self.words) is not tuple or len(self.words) != self.count
                or any(type(w) is not int or not 0 <= w <= 65535 for w in self.words)):
            raise ValueError('Complete declared uint16 block words required')


def assemble(packets, expected_id):
    """Consume one isolated, checksummed 0x74/75/76 burst as mido data bytes.

    No F0/F7, IO, timeout, retry, model interpretation or skipped packets.
    The caller supplies a finite isolated burst from a separately approved reader.
    """
    if type(expected_id) is not int or not 1 <= expected_id <= 207:
        raise ValueError('An explicit block ID is required')
    try:
        stream = iter(packets)
    except TypeError as error:
        raise ValueError('A finite isolated packet iterable is required') from error
    count, words, ended = None, [], False
    for index, data in enumerate(stream):
        if (index >= 1024 or ended or type(data) not in (list, tuple)
                or not 6 <= len(data) <= 4096 or not protocol.valid_reply(data)):
            raise ValueError('Malformed, excessive or trailing broadcast packet')
        fn = data[4]
        if fn == shared.FN_BCAST_HEAD:
            if count is not None or len(data) != 10:
                raise ValueError('Exactly one broadcast header is required')
            eid, count = shared.parse_bcast_head(list(data))
            if eid != expected_id or not 1 <= count <= 16383:
                raise ValueError('Broadcast target or declared count differs')
        elif fn == shared.FN_BCAST_BODY:
            body = data[7:-1]
            if (count is None or tuple(data[5:7]) != (0, 0) or not body
                    or len(body) % 3 or any(b > 3 for b in body[2::3])):
                raise ValueError('Incomplete or unobserved broadcast body layout')
            words.extend(shared.parse_bcast_body(list(data)))
            if len(words) > count:
                raise ValueError('Broadcast exceeds its declared count')
        elif fn == shared.FN_BCAST_END:
            if count is None or len(data) != 6 or len(words) != count:
                raise ValueError('Broadcast end does not complete the declared words')
            ended = True
        else:
            raise ValueError('Unrelated packet is not part of this isolated burst')
    if not ended:
        raise ValueError('Truncated broadcast; no partial or default-filled result')
    return Broadcast(expected_id, count, tuple(words))
