"""Pure edit-buffer rename contract. No device IO or writable capability."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from fm9 import protocol as shared
from . import readonly_protocol as protocol


def _number(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')


def _state(value):
    """Require the complete status-reader surface, not invented missing names."""
    if type(value) is not dict or value.get('connected') is not True:
        raise ValueError('A fresh connected status snapshot is required')
    try:
        count = protocol.preset_count(value['declared_chassis'])
        if type(value['preset_count']) is not int or value['preset_count'] != count:
            raise ValueError('Declared capacity does not match the status snapshot')
        preset, scene, names = value['preset'], value['scene'], value['scenes']
        _number(preset['number'], 0, count - 1, 'Current preset')
        _number(scene['number'], 1, 8, 'Current scene')
        if type(preset['editor']) is not int or preset['editor'] != preset['number']:
            raise ValueError('III editor numbering must match wire numbering')
        if (type(names) is not list or len(names) != 8
                or any(type(row) is not dict for row in names)
                or any(type(row['number']) is not int for row in names)
                or {row['number'] for row in names} != set(range(1, 9))
                or any(type(row['name']) is not str for row in names)):
            raise ValueError('All eight scene names must have been read')
        active = next(row['name'] for row in names if row['number'] == scene['number'])
        if (type(preset['name']) is not str or type(scene['name']) is not str
                or scene['name'] != active or type(value['blocks']) is not list
                or type(value['firmware']) is not str or not value['firmware']):
            raise ValueError('Incomplete or incoherent status snapshot')
        ids = set()
        for block in value['blocks']:
            _number(block['effect_id'], 0, 16383, 'Block ID')
            if (block['effect_id'] in ids or type(block['bypassed']) is not bool
                    or block['channel'] not in ('A', 'B', 'C', 'D')):
                raise ValueError('Incomplete or duplicate block status')
            ids.add(block['effect_id'])
    except (KeyError, TypeError) as error:
        raise ValueError('Incomplete status snapshot') from error
    return value


@dataclass(frozen=True)
class NameEdit:
    """Pinned wire preset, optional one-based scene, exact printable ASCII name.

    Construction is not permission to transmit. No name is truncated,
    transliterated, trimmed or given an implicit prefix.
    """
    preset: int
    name: str
    scene: int | None = None

    def __post_init__(self):
        _number(self.preset, 0, 1023, 'Preset')
        if self.scene is not None:
            _number(self.scene, 1, 8, 'Scene')
        minimum = 1 if self.scene is None else 0
        if (type(self.name) is not str or not minimum <= len(self.name) <= 31
                or self.name != self.name.strip()
                or any(not 32 <= ord(char) <= 126 for char in self.name)):
            raise ValueError('Use printable ASCII without outer spaces, at most 31 characters; '
                             'only scene names may be empty')

    @property
    def kind(self):
        return 'rename_preset' if self.scene is None else 'rename_scene'

    def frame(self):
        """Reuse Gen-3 name packing; product 0x10 only. Does not send it."""
        frame = (shared.build_rename_preset(self.name) if self.scene is None
                 else shared.build_set_scene_name(self.scene - 1, self.name))
        return protocol.envelope(frame[5], frame[6:-2])

    def expected_after(self, before):
        """A strict comparison baseline, not a restore image or write recipe."""
        _state(before)
        if before['preset']['number'] != self.preset:
            raise ValueError('The selected preset differs from the pinned target')
        wanted = deepcopy(before)
        if self.scene is None:
            wanted['preset']['name'] = self.name
        else:
            for row in wanted['scenes']:
                if row['number'] == self.scene:
                    row['name'] = self.name
            if wanted['scene']['number'] == self.scene:
                wanted['scene']['name'] = self.name
        return wanted

    def verify(self, before, after):
        """Exact equality except the requested name; never retry or restore."""
        wanted = self.expected_after(before)
        _state(after)
        if wanted != after:
            raise ValueError('Name readback or another observed state field differs')
        return True

    def preview(self, before):
        wanted = self.expected_after(before)
        previous = (before['preset']['name'] if self.scene is None else
                    next(row['name'] for row in before['scenes'] if row['number'] == self.scene))
        return dict(kind=self.kind, preset=self.preset, scene=self.scene,
                    before=previous, after=self.name, changes=wanted != before,
                    executable=False, stored=False)
