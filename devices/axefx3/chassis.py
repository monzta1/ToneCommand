"""One III control family, with declared chassis storage differences only.

These facts never grant an opcode, firmware profile or memory-write permit.
The current measured writers keep their separate evidence checks.
"""
from dataclasses import dataclass
from types import MappingProxyType


CONTROL_FAMILY = 'axe-fx-iii'
MODEL_BYTE = 0x10
# Name-list layouts, not selector encodings or firmware write aliases.
MODERN_CAB_FIRMWARE = frozenset({'33.00-beta.20261006', '33.00-beta5.20261026'})


@dataclass(frozen=True)
class Chassis:
    name: str | None
    presets: int
    persistent_fullres: int
    retains_user2_with_nam: bool
    control_family: str = CONTROL_FAMILY


CHASSIS = MappingProxyType({
    'mk1': Chassis('mk1', 512, 0, False),
    'mk2': Chassis('mk2', 1024, 64, True),
    'turbo': Chassis('turbo', 1024, 64, True),
})
UNKNOWN = Chassis(None, 512, 0, False)
PRESET_COUNTS = MappingProxyType({key: value.presets for key, value in CHASSIS.items()})


def declared(name, *, allow_unknown=False):
    """A local declaration, never auto-detection or hardware acceptance."""
    if name is None and allow_unknown:
        return UNKNOWN
    if type(name) is not str or name not in CHASSIS:
        raise ValueError('Choose mk1, mk2 or turbo explicitly; no automatic chassis detection')
    return CHASSIS[name]


def modern_cab_metadata(firmware):
    return type(firmware) is str and firmware in MODERN_CAB_FIRMWARE
