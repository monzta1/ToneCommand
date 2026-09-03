"""Parse FM9-Edit .fasBundle files: a preset plus the cabs it depends on,
with every cab's destination stated by the vendor. Issue #42.

A .fasBundle is a plain zip holding a `.bundle` XML Bundle-Map, the preset
as a standard dump .syx, and each user cab as a standard cab .syx. The map
names the device (deviceId 18 = FM9), and pins every cab to the user-cab
Bank and Number the preset's CAB block references, which is exactly the
information the U{n} filename convention only hints at. Verified against a
purchased BoutiqueTones bundle (2025-06 authoring).

This module only parses. The preset goes through presetfile.parse, every
cab through cabfile.parse; nothing that fails validation is returned, and
nothing here touches hardware.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree

from . import cabfile, presetfile
from . import protocol as p


class BundleFileError(ValueError):
    """Written for the person who dragged the bundle in."""


@dataclass
class BundleCab:
    cab: cabfile.CabFile
    raw: bytes
    bank: int                 # 1-based, as FM9-Edit shows it
    number: int               # 1-based within the bank
    name: str
    file: str


@dataclass
class BundleFile:
    preset: presetfile.PresetFile
    preset_raw: bytes
    preset_name: str
    cabs: list[BundleCab] = field(default_factory=list)


def parse(raw: bytes) -> BundleFile:
    if raw[:2] != b"PK":
        raise BundleFileError("not a .fasBundle: the file is not a zip")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise BundleFileError(f"unreadable bundle zip: {exc}") from exc
    names = {i.filename: i for i in zf.infolist()}
    map_name = next((n for n in names if n.rsplit("/", 1)[-1] == ".bundle"),
                    None)
    if map_name is None:
        raise BundleFileError("no Bundle-Map inside; this zip is not an "
                              "FM9-Edit bundle")
    try:
        root = ElementTree.fromstring(zf.read(map_name).decode(
            "utf-8", "replace"))
    except ElementTree.ParseError as exc:
        raise BundleFileError(f"the Bundle-Map is not readable: {exc}")
    if root.tag != "Bundle-Map":
        raise BundleFileError("the map inside is not a Bundle-Map")
    dev = root.find("Device")
    device_id = int(dev.get("deviceId", "-1")) if dev is not None else -1
    if device_id != p.MODEL_FM9:
        raise BundleFileError(
            f"this bundle targets device id {device_id}, not the FM9 "
            f"({p.MODEL_FM9}); bundles are device-specific")

    def _read(rel: str) -> bytes:
        hit = next((n for n in names if n == rel
                    or n.endswith("/" + rel)), None)
        if hit is None:
            raise BundleFileError(
                f"the map names {rel!r} but the bundle does not contain it")
        return zf.read(hit)

    pel = root.find("Preset")
    if pel is None or not pel.get("File"):
        raise BundleFileError("the Bundle-Map names no preset")
    preset_raw = _read(pel.get("File"))
    try:
        pf = presetfile.parse(preset_raw)
    except presetfile.PresetFileError as exc:
        raise BundleFileError(f"the bundled preset is invalid: {exc}")

    cabs: list[BundleCab] = []
    seen: set[str] = set()
    for cel in root.findall("CabData"):
        file_rel = cel.get("File") or ""
        try:
            bank = int(cel.get("Bank", "0"))
            number = int(cel.get("Number", "0"))
        except ValueError:
            raise BundleFileError(
                f"cab entry {file_rel!r} carries a non-numeric destination")
        if bank < 1 or number < 1:
            raise BundleFileError(
                f"cab entry {file_rel!r} has no usable Bank/Number")
        key = f"{bank}:{number}:{file_rel}"
        if key in seen:
            continue           # scenes reusing a cab repeat the entry
        seen.add(key)
        cab_raw = _read(file_rel)
        try:
            cf = cabfile.parse(cab_raw, file_rel)
        except cabfile.CabFileError as exc:
            raise BundleFileError(
                f"bundled cab {file_rel!r} is invalid: {exc}")
        cabs.append(BundleCab(cab=cf, raw=cab_raw, bank=bank, number=number,
                              name=cel.get("Name") or cf.label,
                              file=file_rel))
    return BundleFile(preset=pf, preset_raw=preset_raw,
                      preset_name=pel.get("Name") or pf.name, cabs=cabs)
