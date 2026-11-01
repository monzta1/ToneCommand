"""Opaque-preserving observation validation and injected read-only settling.

Not registered in the app. No adapter, transport, writer, provider or model map
is imported. The caller must prove fresh read provenance and transport rights.
"""
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import json

from . import protocol
from .observed_words import Broadcast


FIELDS = frozenset({'identity', 'variant', 'firmware', 'preset', 'scene',
                    'status', 'grid', 'bulk', 'modifiers', 'scenes'})


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _name(value, limit=32):
    return type(value) is str and len(value) <= limit


def _keys(value, expected):
    return type(value) is dict and set(value) == set(expected)


@dataclass(frozen=True)
class Observation:
    """Detached canonical data, not a backup image or an approval token."""
    _json: str = field(repr=False)

    def data(self):
        return json.loads(self._json)

    @property
    def digest(self):
        return hashlib.sha256(self._json.encode('utf-8')).hexdigest()

    @property
    def target(self):
        d = self.data()
        return tuple(d['identity']), d['variant'], d['preset'][0], d['scene']


def observe(raw):
    """Validate every required observed surface, keeping opaque uint16 words.

    All status blocks, including system 200/201, need counted broadcasts.
    All 32 modifier broadcasts are required, including unused/stale words.
    Counts establish structural completeness, not a firmware-specific layout.
    """
    if not _keys(raw, FIELDS):
        raise ValueError('All observation surfaces are required; no dropped extra fields')
    identity = raw['identity']
    if (type(identity) not in (list, tuple) or not 8 <= len(identity) <= 256
            or not protocol.valid_reply(identity) or identity[4] != 8):
        raise ValueError('Complete valid product 0x10 identity reply required')
    capacity = protocol.preset_count(raw['variant'])
    preset, scene, names = raw['preset'], raw['scene'], raw['scenes']
    if (type(preset) not in (list, tuple) or len(preset) != 2
            or not _integer(preset[0], 0, capacity - 1) or not _name(preset[1])
            or not _integer(scene, 1, 8) or not _name(raw['firmware'], 80)
            or not raw['firmware']):
        raise ValueError('Complete current target and declared capacity required')
    if (type(names) is not list or len(names) != 8
            or any(type(n) not in (list, tuple) or len(n) != 2
                   or not _integer(n[0], 1, 8) or n[0] != i + 1 or not _name(n[1])
                   for i, n in enumerate(names))):
        raise ValueError('All eight scene names must have been observed in order')
    status = raw['status']
    if type(status) is not list or not 2 <= len(status) <= 86:
        raise ValueError('Complete block inventory required')
    ids = []
    for b in status:
        if (not _keys(b, ('effect_id', 'channel', 'bypassed', 'channels_supported'))
                or not _integer(b['effect_id'], 1, 207)
                or type(b['channels_supported']) is not int or b['channels_supported'] not in (1, 2, 4)
                or not _integer(b['channel'], 0, b['channels_supported'] - 1)
                or type(b['bypassed']) is not bool):
            raise ValueError('Incomplete block status; no guessed channels or bypass')
        ids.append(b['effect_id'])
    if len(ids) != len(set(ids)) or not {200, 201} <= set(ids):
        raise ValueError('Unique blocks and both opaque system blocks are required')
    grid = raw['grid']
    if type(grid) is not list or len(grid) > 84:
        raise ValueError('Complete six-row, fourteen-column occupied-cell grid required')
    positions, grid_ids = set(), []
    for cell in grid:
        if (not _keys(cell, ('row', 'col', 'effect_id', 'is_shunt', 'cable_in_mask'))
                or not _integer(cell['row'], 0, 5) or not _integer(cell['col'], 0, 13)
                or type(cell['is_shunt']) is not bool
                or not _integer(cell['cable_in_mask'], 0, 126) or cell['cable_in_mask'] & 1):
            raise ValueError('Malformed grid coordinate or observed cable mask')
        position = cell['row'], cell['col']
        if position in positions:
            raise ValueError('Duplicate grid position')
        positions.add(position)
        if cell['is_shunt']:
            if cell['effect_id'] is not None:
                raise ValueError('A shunt cannot masquerade as an effect instance')
        elif _integer(cell['effect_id'], 1, 199) or _integer(cell['effect_id'], 202, 207):
            grid_ids.append(cell['effect_id'])
        else:
            raise ValueError('Occupied effect cell needs its actual instance ID')
    if len(grid_ids) != len(set(grid_ids)) or set(grid_ids) != set(ids) - {200, 201}:
        raise ValueError('Grid and block inventories differ; do not flatten or invent cells')
    bulk = raw['bulk']
    if not _keys(bulk, (str(eid) for eid in ids)):
        raise ValueError('Every observed block needs exactly one complete broadcast')
    for eid in ids:
        b = bulk[str(eid)]
        if type(b) is not Broadcast or b.effect_id != eid:
            raise ValueError('Counted broadcast target differs from block inventory')
    mods = raw['modifiers']
    if (type(mods) is not list or len(mods) != 32
            or any(type(b) is not Broadcast or b.effect_id != i + 3 or b.count != 25
                   for i, b in enumerate(mods))):
        raise ValueError('All 32 complete, ordered 25-word modifier records required')
    out = dict(identity=list(identity), variant=raw['variant'], firmware=raw['firmware'],
        preset=list(preset), scene=scene, scenes=[list(n) for n in names],
        status=sorted(deepcopy(status), key=lambda b: b['effect_id']),
        grid=sorted(deepcopy(grid), key=lambda c: (c['row'], c['col'])),
        bulk={str(eid): list(bulk[str(eid)].words) for eid in ids},
        broadcast_counts={str(eid): bulk[str(eid)].count for eid in ids},
        modifiers=[list(b.words) for b in mods])
    return Observation(json.dumps(out, sort_keys=True, separators=(',', ':'), ensure_ascii=False))


def capture(read, *, max_reads=4):
    """Require two consecutive equal complete observations of the same target.

    Only complete but unequal reads settle again. Bad data, read errors or a
    target/identity change stop immediately. Never retry a write or return a
    last-known/default state. The injected read callback must perform fresh
    reads and check its target before/after assembling each observation.
    """
    if not callable(read) or not _integer(max_reads, 2, 8):
        raise ValueError('A fresh read callback and a 2..8 read bound are required')
    previous = observe(read())
    target = previous.target
    for _ in range(max_reads - 1):
        current = observe(read())
        if current.target != target:
            raise ValueError('Identity or target changed during observation; stop')
        if current == previous:
            return current
        previous = current
    raise ValueError('Complete preset observations did not settle; no snapshot returned')
