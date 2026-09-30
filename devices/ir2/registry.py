"""The BOSS IR-2 parameter registry.

SOURCE, AND WHY IT IS TRUSTED. Every row is transcribed from the address map
BOSS ships inside its own IR-2 IR Loader (Contents/Resources/html/js/config/
address_map.js and product_setting.js, app dated 2023-09-29). That is the
vendor's own table, not a community guess, and the parts of it this project
uses were independently confirmed on the unit before this file was written:

- PATCH_COM's seven parameters were found on hardware by over-reading the
  block, and its AMP row's 0..10 range was found by writing 0x00 to 0x0D and
  watching everything above 0x0A clamp. The vendor table says max 10.
- SYSTEM_COM's 12 bytes decoded exactly as the table's mix of one-byte and
  nibble-pair fields predicted, including all three USB levels reading 100.

Where the two disagreed, nothing would have been shipped. They did not.

TAPERS ARE NOT PUBLISHED, so this module does not invent one. The device
carries 0..127 for its continuous parameters and says nothing about what
curve maps that to the panel's markings. `to_display` therefore refuses,
for the same reason the HeadRush registry's does: the one place a caller
would otherwise quietly write the assumption themselves.
"""
from __future__ import annotations

from dataclasses import dataclass


class NotMeasured(RuntimeError):
    """The device names a value's range but not its curve."""


@dataclass(frozen=True)
class Param:
    name: str            # the panel's word for it
    offset: int          # byte offset inside its block
    lo: int
    hi: int
    init: int
    nibbles: int = 1     # 1 = one byte; 2 = INTEGER2x4, a nibble pair
    options: tuple[str, ...] = ()

    @property
    def is_enum(self) -> bool:
        return bool(self.options)

    def validate(self, value: int) -> int:
        if not self.lo <= value <= self.hi:
            raise ValueError(
                f"{self.name} takes {self.lo} to {self.hi}, not {value}")
        return int(value)

    def to_display(self, value: int) -> float:
        if self.is_enum:
            return float(value)
        raise NotMeasured(
            f"{self.name} carries 0..127 on the wire and the IR-2 does not "
            "publish the curve behind its panel markings. Measure it on the "
            "unit before converting, or use the wire value as the wire value.")


#: The eleven amp voicings, in device order, with the factory cab IR each one
#: ships with (product_setting.js `cabFileList`). The cab names are the
#: vendor's own file names, kept verbatim so they can be matched against a
#: real IR library rather than paraphrased into something unsearchable.
AMPS: tuple[tuple[str, str], ...] = (
    ("CLEAN",   "V-Type 112 C R-121 Balanced Celestion.wav"),
    ("TWN",     "A-Type 212 O Lo-Gn 421+121 Celestion.wav"),
    ("TWEED",   "G10 Gold 410 C Lo-Gn 121+57 Celestion.wav"),
    ("DIAMOND", "Cel Blue 212 O Hi-Gn 421+121 Celestion.wav"),
    ("CRUNCH",  "G12-65 212 O Lo-Gn 421+121 Celestion.wav"),
    ("BRIT",    "G12M-Heritage 412 C MD421 Balanced Celestion.wav"),
    ("HI-GAIN", "G12M Creambk 412 C MD421 Balanced Celestion.wav"),
    ("SLDN",    "V30 412 C MD421 Balanced Celestion.wav"),
    ("BROWN",   "G12M-Heritage 412 C MD421 Balanced Celestion.wav"),
    ("MODDED",  "G12K-100 412 C MD421 Balanced Celestion.wav"),
    ("RFIER",   "V30 412 C MD421 Balanced Celestion.wav"),
)
AMP_NAMES: tuple[str, ...] = tuple(n for n, _ in AMPS)

#: PATCH block, base 0x20000000. The seven physical knobs.
PATCH_PARAMS: tuple[Param, ...] = (
    Param("BASS",     0, 0, 127, 64),
    Param("MIDDLE",   1, 0, 127, 64),
    Param("TREBLE",   2, 0, 127, 64),
    Param("LEVEL",    3, 0, 127, 64),
    Param("GAIN",     4, 0, 127, 64),
    Param("AMBIENCE", 5, 0, 127, 64),
    Param("AMP",      6, 0,  10,  0, options=AMP_NAMES),
)

#: SYSTEM block, base 0x10000000.
SYSTEM_PARAMS: tuple[Param, ...] = (
    Param("AMP_CAB_SW", 0, 0, 2, 0,
          options=("AMP ON / CAB ON", "AMP ON / CAB OFF", "AMP OFF / CAB ON")),
    Param("AMBIENCE_TYPE", 1, 0, 2, 0, options=("ROOM", "HALL", "PLATE")),
    Param("OUTPUT_SELECT", 2, 0, 12, 0, options=(
        "LINE", "JC-120 RETURN", "JC-120 INPUT",
        "KATANA-100 RETURN", "KATANA-100 INPUT",
        "NEXTONE Artist RETURN", "NEXTONE Artist INPUT",
        "TUBE COMBO 112 RETURN", "TUBE COMBO 112 INPUT",
        "TUBE COMBO 212 RETURN", "TUBE COMBO 212 INPUT",
        "TUBE STACK 412 RETURN", "TUBE STACK 412 INPUT")),
    Param("SEND_RET_MODE", 3, 0, 1, 0, options=("MONO", "STEREO")),
    Param("USB_MODE", 4, 0, 1, 1, options=("GENERIC", "VENDOR")),
    Param("USB_OUT_LEVEL", 5, 0, 200, 100, nibbles=2),
    Param("USB_IN_LEVEL", 7, 0, 200, 100, nibbles=2),
    Param("USB_LOOPBACK_SW", 9, 0, 1, 0, options=("OFF", "ON")),
    Param("USB_LOOPBACK_LEVEL", 10, 0, 200, 100, nibbles=2),
)

#: SETUP block, base 0x00000000. Which of the two stored patches is live;
#: the footswitch toggles it, and the pedal announces the change.
SETUP_PARAMS: tuple[Param, ...] = (
    Param("PATCH_NUMBER", 0, 0, 1, 0),
)

_BY_NAME = {p.name: p for p in PATCH_PARAMS + SYSTEM_PARAMS + SETUP_PARAMS}


def resolve(name: str) -> Param:
    key = name.upper().replace(" ", "_").replace("-", "_")
    if key not in _BY_NAME:
        raise KeyError(f"the IR-2 has no parameter named {name!r}; it has "
                       f"{', '.join(sorted(_BY_NAME))}")
    return _BY_NAME[key]


def amp_ordinal(name: str) -> int:
    """The AMP value for a voicing name. Exact, case-insensitive."""
    want = name.strip().upper()
    for i, n in enumerate(AMP_NAMES):
        if n == want:
            return i
    raise KeyError(f"the IR-2 has no amp called {name!r}; it has "
                   f"{', '.join(AMP_NAMES)}")


def decode_nibbles(data: list[int], p: Param) -> int:
    """INTEGER2x4: one value carried as two 4-bit nibbles, high first."""
    if p.nibbles == 1:
        return int(data[p.offset])
    hi, lo = data[p.offset], data[p.offset + 1]
    return (hi << 4) | lo


def encode_nibbles(value: int, p: Param) -> list[int]:
    if p.nibbles == 1:
        return [int(value)]
    return [(int(value) >> 4) & 0x0F, int(value) & 0x0F]
