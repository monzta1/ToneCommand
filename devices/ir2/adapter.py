"""The BOSS IR-2 on the device adapter contract.

WHAT THIS DEVICE IS. A compact pedal: one amp voicing chosen from eleven,
five tone knobs, an ambience control, two stored patches and twelve IR
slots. It has no scenes, no effect blocks, no signal grid and no preset
library in the FM9 sense, so most of the contract is declined rather than
faked. What it does have is unusually honest: every parameter reads back,
every write verifies, and the pedal announces its own panel changes without
being asked.

VERIFIED ON HARDWARE 2026-09-29 (kb/IR2_PROTOCOL.md), in this order:
reads matched what the pedal pushed byte for byte; writes to all six
continuous knobs were accepted, read back and restored; AMP accepted 0x00
to 0x0A and clamped everything above. The adapter claims nothing that was
not done on the unit.

NOT DONE, AND THEREFORE REFUSED IN ONE LINE. The IR file transfer path is
not decoded. The vendor's address map names IRDATA SIZE, FILE and DATA
regions, so the shape is known, but no byte of an IR has been moved by this
code and none will be until that path is proven. `install_capture` refuses
before any frame exists, exactly as the ToneX adapter's does, so invariant 0
holds by construction rather than by care.
"""
from __future__ import annotations

from typing import Any

from fm9.adapter import (Capabilities, CaptureCapabilities, CaptureSlot,
                         ReadPath, Topology)

from . import protocol as p
from . import registry as reg
from .client import MidiClient

#: One line, naming what owns the path and the rule that keeps it closed.
INSTALL_REFUSED = (
    "the IR-2 IR transfer path is not decoded yet and stays closed under "
    "invariant 0, never brick; nothing was sent. Load IRs with the BOSS "
    "IR-2 IR Loader for now")

NO_SCENES = "the IR-2 has no scenes; it has two stored patches, 0 and 1"
NO_BLOCKS = ("the IR-2 has no effect blocks to bypass or switch channels on; "
             "it is one amp, one cab and one ambience")


class IR2Adapter:
    """Satisfies fm9.adapter.DeviceAdapter."""

    CAPABILITIES = Capabilities(
        # reads were proven to match the pedal's own pushes, byte for byte
        read_path=ReadPath.DEVICE,
        # it announces every knob turn and footswitch press unprompted
        observes_foreign_writes=True,
        reads_slot_names=True,        # the 32-byte IR slot names read back
        reads_slot_state=True,
        verifies_writes=True,         # every write is read back before it counts
        has_scenes=False,
        stores_presets=False,         # two fixed patches, no store command decoded
        topology=Topology.FIXED,
        has_modifiers=False,
        installs_files=False,
        can_rename=False,
        composable_scene_slots=False,
        plays_captures=True,          # twelve IR slots, listed; none installable yet
        # #198: seven parameters named on the enclosure, and no published
        # taper, so the planner and the apply path address them by name.
        has_named_params=True,
    )

    def __init__(self, client=None):
        self.io = client if client is not None else MidiClient()
        self.undecoded: set[str] = {
            "IR-2: the IR transfer path (IRDATA SIZE/FILE/DATA) is named by "
            "the vendor map but no byte of it has been proven here.",
        }

    # --- identity ---------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return self.CAPABILITIES

    def firmware_label(self) -> str:
        # The identity reply's revision field is all zeros on this unit, so
        # there is nothing honest to report.
        return ""

    def evidence(self) -> dict:
        return {"surface": "Roland addressed SysEx, model 01 05 09; reads "
                           "verified against the pedal's own pushes "
                           "(kb/IR2_PROTOCOL.md)",
                "write_path": "DT1 with read-back verification, proven on "
                              "all six continuous knobs and AMP"}

    # --- state ------------------------------------------------------------

    def patch(self) -> dict:
        """Every knob, named, as the unit reports it right now."""
        data = self.io.read(p.PATCH, len(reg.PATCH_PARAMS))
        out = {}
        for spec in reg.PATCH_PARAMS:
            value = reg.decode_nibbles(data, spec)
            out[spec.name] = (spec.options[value]
                              if spec.is_enum and value < len(spec.options)
                              else value)
        return out

    def system(self) -> dict:
        data = self.io.read(p.SYSTEM, 12)
        out = {}
        for spec in reg.SYSTEM_PARAMS:
            value = reg.decode_nibbles(data, spec)
            out[spec.name] = (spec.options[value]
                              if spec.is_enum and value < len(spec.options)
                              else value)
        return out

    def status_dump(self) -> dict:
        return {"device": "ir2", "patch": self.patch(), "system": self.system(),
                "patch_number": self.io.read(p.SETUP, 1)[0]}

    def current_preset(self) -> tuple:
        """(patch number, amp name). The IR-2's two patches are its only
        preset concept, and the amp voicing is the closest thing it has to
        a preset name."""
        number = self.io.read(p.SETUP, 1)[0]
        return number, self.patch()["AMP"]

    def observed_changes(self) -> list[dict]:
        """What the player changed on the pedal since the last call."""
        rows = []
        for addr, data in self.io.drain_events():
            if p.PATCH <= addr < p.PATCH + len(reg.PATCH_PARAMS):
                spec = reg.PATCH_PARAMS[addr - p.PATCH]
                value = data[0]
                rows.append({"param": spec.name,
                             "value": (spec.options[value]
                                       if spec.is_enum and value < len(spec.options)
                                       else value)})
            elif addr == p.SETUP:
                rows.append({"param": "PATCH_NUMBER", "value": data[0]})
        return rows

    # --- writes, all verified ---------------------------------------------

    def set_param(self, name: str, value: Any) -> dict:
        """Set one named parameter and report what the unit says it now is.

        An enum may be given by name ("BROWN") or ordinal. Out of range is
        refused HERE, before anything is sent, because the pedal clamps
        silently and a clamp that reached the wire would be reported as a
        success by read-back.
        """
        spec = reg.resolve(name)
        if spec.is_enum and isinstance(value, str):
            if spec.name == "AMP":
                value = reg.amp_ordinal(value)
            else:
                want = value.strip().upper()
                match = [i for i, o in enumerate(spec.options) if o.upper() == want]
                if not match:
                    raise KeyError(f"{spec.name} has no setting {value!r}; it "
                                   f"has {', '.join(spec.options)}")
                value = match[0]
        spec.validate(int(value))
        base = p.PATCH if spec in reg.PATCH_PARAMS else (
            p.SYSTEM if spec in reg.SYSTEM_PARAMS else p.SETUP)
        back = self.io.write(base + spec.offset,
                             reg.encode_nibbles(int(value), spec))
        got = reg.decode_nibbles([0] * spec.offset + list(back), spec)
        return {"param": spec.name, "value": got,
                "label": spec.options[got] if spec.is_enum and got < len(spec.options) else None}

    # --- NamedParams (#198): the device's own vocabulary ------------------

    def named_params(self) -> list:
        """Every parameter this pedal has, as the planner is told about it.

        AMP carries its options AND the factory cab each voicing ships with,
        because "which amp" is the one choice that decides the sound here and
        the cab is half of it. The names are the vendor's own, verbatim, so
        they can be matched against a real IR library rather than paraphrased
        into something unsearchable.
        """
        out = []
        for spec in reg.PATCH_PARAMS:
            row = {"name": spec.name, "lo": spec.lo, "hi": spec.hi,
                   "init": spec.init, "options": list(spec.options)}
            if spec.name == "AMP":
                row["option_cabs"] = {n: cab for n, cab in reg.AMPS}
            out.append(row)
        return out

    def set_named_param(self, name: str, value: Any) -> dict:
        return self.set_param(name, value)

    def set_amp(self, name_or_ordinal: Any) -> dict:
        """The one action worth naming on this device."""
        return self.set_param("AMP", name_or_ordinal)

    def set_params_batch(self, items: Any) -> list:
        """Each write verifies on its own. A failure stops the batch and says
        which item it was, rather than reporting a partial run as success."""
        out = []
        for i, item in enumerate(items):
            name = item["name"] if isinstance(item, dict) else item[0]
            value = item["value"] if isinstance(item, dict) else item[1]
            try:
                out.append(self.set_param(name, value))
            except Exception as e:                    # noqa: BLE001  re-raised with position
                raise type(e)(f"item {i} ({name}): {e}") from e
        return out

    def select_preset(self, preset: int) -> dict:
        """The IR-2's two stored patches, 0 and 1. This is what the
        footswitch does."""
        return self.set_param("PATCH_NUMBER", int(preset))

    # --- IR slots: listed, never written ----------------------------------

    def capture_capabilities(self) -> CaptureCapabilities:
        # an empty whitelist: nothing may be written, by declaration as well
        # as by construction
        return CaptureCapabilities((".wav",), p.IR_SLOTS, frozenset())

    def list_captures(self) -> list:
        """USER 1 to USER 11, numbered as the pedal numbers them.

        An earlier version listed twelve slots starting at zero, which put a
        staging region the vendor's editor never touches at the top of the
        list looking like an empty user slot, and pushed every real slot's
        number out by one at the far end.
        """
        rows = []
        for slot in range(p.IR_FIRST_SLOT, p.IR_FIRST_SLOT + p.IR_SLOTS):
            raw = self.io.read(p.ir_slot_addr(slot, p.IR_NAME), 32)
            name = bytes(raw).decode("ascii", "replace").rstrip()
            rows.append(CaptureSlot(slot=slot, occupied=bool(name),
                                    name=name or None, record=None))
        return rows

    def install_capture(self, record: Any, raw: bytes, slot: int):
        raise NotImplementedError(INSTALL_REFUSED)

    def remove_capture(self, slot: int):
        raise NotImplementedError(INSTALL_REFUSED)

    def _slot_row(self, slot: int):
        for c in self.list_captures():
            if c.slot == int(slot):
                return c
        raise KeyError(f"the IR-2 has USER slots {p.IR_FIRST_SLOT} to "
                       f"{p.IR_FIRST_SLOT + p.IR_SLOTS - 1}, not {slot}")

    def slot_name(self, preset: int) -> str:
        return self._slot_row(preset).name or ""

    def is_slot_empty(self, preset: int) -> bool:
        return not self._slot_row(preset).occupied

    def scan_slots(self, start: int = p.IR_FIRST_SLOT,
                   end: int = p.IR_FIRST_SLOT + p.IR_SLOTS - 1) -> list:
        return [{"slot": c.slot, "name": c.name or "", "empty": not c.occupied}
                for c in self.list_captures()
                if start <= c.slot <= end]

    # --- what this device has no concept of, stated rather than faked -----

    def set_scene(self, scene_1based: int):
        raise NotImplementedError(NO_SCENES)

    def scene_name(self, scene: Any = None):
        raise NotImplementedError(NO_SCENES)

    def set_bypass(self, effect_id: int, bypassed: bool):
        raise NotImplementedError(NO_BLOCKS)

    def set_channel(self, effect_id: int, channel_0based: int):
        raise NotImplementedError(NO_BLOCKS)

    def bulk_read(self, effect_id: int, timeout: float = 1.5):
        raise NotImplementedError(NO_BLOCKS)

    def store_preset(self, slot: int):
        raise NotImplementedError(
            "the IR-2's store command is not decoded; its two patches are "
            "written live and the pedal keeps them. Nothing was sent.")

    def set_param_display(self, spec: Any, display_value: float):
        raise NotImplementedError(
            "the IR-2 does not publish the curve behind its panel markings, "
            "so a display value cannot be converted honestly. Use set_param "
            "with the 0..127 wire value.")

    def set_param_ordinal(self, spec: Any, ordinal: int):
        return self.set_param(getattr(spec, "name", str(spec)), int(ordinal))

    def get_param_display(self, spec: Any):
        raise NotImplementedError(
            "the IR-2 does not publish its taper; read the wire value with "
            "patch() instead of inventing a display number.")

    def close(self):
        self.io.close()
