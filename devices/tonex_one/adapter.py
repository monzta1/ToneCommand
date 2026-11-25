"""The IK Multimedia ToneX One on the device adapter contract.

WHAT THIS DEVICE IS. A one-switch pedal holding twenty presets. Three of
them sit in slots: A and B in dual mode (the switch flips between them, the
amp is never off) and C in stomp mode (the switch turns it on and off). A
preset is a tone model (an amp, maybe a cab) plus a gate, compressor, EQ,
reverb, modulation and delay, 109 settings in all.

WHAT IS PROVEN ON A REAL ONE (fw 1.3.17, 2026-11-25, kb/TONEX_ONE_PROTOCOL.md):
reading the state and all twenty presets; switching the active slot and
reading it back; changing a setting on the preset playing (EQ treble
5.0 -> 5.5 -> 5.0, twice) and reading it back from the preset. The pedal
saves on its own: a change is kept as soon as it is made, there is no edit
buffer to discard. So before the first change of a session the adapter
writes a backup of all twenty presets and the state to disk.

WHAT IT DOES NOT DO. Load a new tone model onto the pedal, rename a preset,
or change the five settings in params.py marked `blocked`. Tone models are
loaded with IK's TONEX Editor.

THE SURFACE, AS NAMED PARAMETERS. The preset playing's settings by name
(EQ_TREBLE, MODEL_GAIN, REVERB_MODEL, ...), plus the pedal's own controls:
SLOT_A, SLOT_B, SLOT_C (which preset sits there, by name), ACTIVE_SLOT,
MODE (DUAL or STOMP), CAB_SIM (ON or OFF) and INPUT_TRIM.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from fm9.adapter import Capabilities, ReadPath, Topology

from . import params as P
from . import planning as _planning
from . import protocol as p
from .client import ToneXOneClient

SWITCH = ("OFF", "ON")
POSITION = ("PRE AMP", "POST AMP")
OPTIONS: dict[str, tuple] = {
    "REVERB_POSITION": ("POST AMP", "LAST"),
    "DELAY_DIGITAL_MODE": ("NORMAL", "PING PONG"),
    "DELAY_TAPE_MODE": ("NORMAL", "PING PONG"),
}
PEDAL = ("SLOT_A", "SLOT_B", "SLOT_C", "ACTIVE_SLOT", "MODE", "CAB_SIM", "INPUT_TRIM")
ACTIVE = ("A", "B", "STOMP")


def backup_dir() -> Path:
    return Path(os.environ.get("TONECOMMAND_TONEX_ONE_BACKUPS")
                or Path.home() / ".tonecommand" / "tonex_one" / "backups")


def _options(prm: P.Param) -> tuple | None:
    if prm.name in OPTIONS:
        return OPTIONS[prm.name]
    if prm.options:
        return prm.options
    if prm.kind == "switch":
        return POSITION if prm.name.endswith("_POST") else SWITCH
    return None


class ToneXOneAdapter:
    """Satisfies fm9.adapter.DeviceAdapter (named parameters)."""

    CAPABILITIES = Capabilities(
        read_path=ReadPath.DEVICE,
        observes_foreign_writes=True,     # the pedal pushes its state on a footswitch press
        reads_slot_names=True,
        reads_slot_state=True,
        verifies_writes=True,             # every change is read back from the pedal
        has_scenes=False,
        stores_presets=False,             # it saves on its own; there is no store
        topology=Topology.FIXED,
        has_named_params=True,
    )
    LABEL = "ToneX One"
    #: #334: this device's prompt, schema and validator (server.named_planning)
    PLANNING = _planning

    def __init__(self, client=None):
        self.io = client if client is not None else ToneXOneClient()
        self._names: dict[int, str] = {}
        self._tags: dict[int, dict] = {}
        self._backed_up = False
        self.backup_path: Path | None = None

    # --- identity ---------------------------------------------------------

    def capabilities(self) -> Capabilities:
        return self.CAPABILITIES

    def firmware_label(self) -> str:
        return self.io.firmware or ""

    def evidence(self) -> dict:
        return {"surface": "USB CDC serial, HDLC frames (kb/TONEX_ONE_PROTOCOL.md)",
                "write_path": "one setting at a time, and the pedal state; each "
                              "read back from the pedal"}

    # --- reading ----------------------------------------------------------

    def preset_names(self) -> dict[int, str]:
        """All twenty, read once per connection (a name changes only in the
        TONEX Editor, which cannot hold the link while ToneCommand does)."""
        if len(self._names) < p.PRESETS:
            for i in range(p.PRESETS):
                if i not in self._names:
                    pr = self.io.read_preset(i)
                    self._names[i], self._tags[i] = pr.name, pr.tags
        return dict(self._names)

    def preset_tags(self, index: int) -> dict:
        self.preset_names()
        return dict(self._tags.get(index, {}))

    def _label(self, index: int) -> str:
        return f"{index + 1} {self.preset_names().get(index, '?')}"

    def slot_options(self) -> list[str]:
        names = self.preset_names()
        return [f"{i + 1} {names[i]}" for i in range(p.PRESETS)]

    def state(self) -> p.State:
        return self.io.read_state()

    def patch(self) -> dict:
        st = self.state()
        pr = self.io.read_preset(st.active_preset)
        out: dict[str, Any] = {
            "SLOT_A": self._label(st.slot_a), "SLOT_B": self._label(st.slot_b),
            "SLOT_C": self._label(st.slot_c),
            "ACTIVE_SLOT": ACTIVE[min(st.current_slot, 2)],
            "MODE": "STOMP" if st.stomp_mode else "DUAL",
            "CAB_SIM": "OFF" if st.cab_bypass else "ON",
            "INPUT_TRIM": st.input_trim,
        }
        for prm in P.PARAMS:
            if prm.blocked:
                continue
            v = pr.params[prm.index]
            opts = _options(prm)
            out[prm.name] = (opts[int(round(v))] if opts and 0 <= int(round(v)) < len(opts)
                             else round(v, 3))
        return out

    def current_preset(self) -> tuple:
        st = self.state()
        return st.active_preset + 1, self.preset_names().get(st.active_preset, "")

    def status_dump(self) -> dict:
        st = self.state()
        return {"device": "tonex_one", "firmware": self.firmware_label(),
                "slots": {"A": st.slot_a + 1, "B": st.slot_b + 1, "C": st.slot_c + 1},
                "active_slot": ACTIVE[min(st.current_slot, 2)],
                "mode": "STOMP" if st.stomp_mode else "DUAL"}

    def observed_changes(self) -> list[dict]:
        rows = []
        for m in self.io.drain_events():
            if m.type == p.T_STATE:
                st = p.State(m.payload[m.body_at:])
                try:
                    st.check()
                except p.ProtocolError:
                    continue
                rows.append({"param": "ACTIVE_SLOT", "value": ACTIVE[min(st.current_slot, 2)]})
        return rows

    # --- NamedParams --------------------------------------------------------

    def named_params(self) -> list:
        slots = self.slot_options()
        out = [
            {"name": "SLOT_A", "lo": 1, "hi": p.PRESETS, "init": None, "options": slots,
             "group": "Pedal", "about": "preset in slot A (dual mode)"},
            {"name": "SLOT_B", "lo": 1, "hi": p.PRESETS, "init": None, "options": slots,
             "group": "Pedal", "about": "preset in slot B (dual mode)"},
            {"name": "SLOT_C", "lo": 1, "hi": p.PRESETS, "init": None, "options": slots,
             "group": "Pedal", "about": "preset in the stomp slot"},
            {"name": "ACTIVE_SLOT", "lo": 0, "hi": 0, "init": None, "options": list(ACTIVE),
             "group": "Pedal", "about": "which slot is playing"},
            {"name": "MODE", "lo": 0, "hi": 0, "init": None, "options": ["DUAL", "STOMP"],
             "group": "Pedal", "about": "dual: the switch flips A and B; stomp: it turns the stomp slot on and off"},
            {"name": "CAB_SIM", "lo": 0, "hi": 0, "init": None, "options": ["ON", "OFF"],
             "group": "Pedal", "about": "OFF bypasses every cab, for a real cab or a cab sim after the pedal"},
            {"name": "INPUT_TRIM", "lo": -15.0, "hi": 15.0, "init": 0.0, "options": [],
             "group": "Pedal", "about": "input level into the pedal, dB"},
        ]
        for prm in P.PARAMS:
            if prm.blocked:
                continue
            opts = _options(prm)
            out.append({"name": prm.name, "lo": prm.lo, "hi": prm.hi, "init": None,
                        "options": list(opts) if opts else [],
                        "group": prm.name.split("_")[0], "about": prm.short})
        return out

    def _backup_once(self) -> None:
        """Every preset and the state, to disk, before the first change of a
        session: the pedal keeps every change at once, so this file is the
        way back."""
        if self._backed_up:
            return
        st = self.state()
        presets = {}
        for i in range(p.PRESETS):
            pr = self.io.read_preset(i)
            presets[i + 1] = {"name": pr.name, "tags": pr.tags,
                              "settings": {prm.name: pr.params[prm.index] for prm in P.PARAMS}}
        d = backup_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"tonex_one_{time.strftime('%Y-%m-%d_%H%M%S')}.json"
        path.write_text(json.dumps({
            "firmware": self.firmware_label(),
            "state": {"slot_a": st.slot_a + 1, "slot_b": st.slot_b + 1,
                      "slot_c": st.slot_c + 1, "active_slot": ACTIVE[min(st.current_slot, 2)],
                      "mode": "STOMP" if st.stomp_mode else "DUAL",
                      "cab_sim": "OFF" if st.cab_bypass else "ON",
                      "input_trim": st.input_trim, "state_hex": st.raw.hex()},
            "presets": presets}, indent=1), encoding="utf-8")
        self.backup_path = path
        self._backed_up = True

    def _preset_index(self, value: Any) -> int:
        """A preset by number (1..20), '7 1CHAIN' or its name."""
        if isinstance(value, (int, float)):
            n = int(value)
        else:
            s = str(value).strip()
            head = s.split(" ", 1)[0]
            if head.isdigit():
                n = int(head)
            else:
                names = {v.upper(): k for k, v in self.preset_names().items()}
                if s.upper() not in names:
                    raise KeyError(f"no preset named {value!r} on the ToneX One")
                return names[s.upper()]
        if not 1 <= n <= p.PRESETS:
            raise KeyError(f"presets are 1 to {p.PRESETS}, got {n}")
        return n - 1

    def set_param(self, name: str, value: Any) -> dict:
        key = str(name).strip().upper().replace(" ", "_").replace("-", "_")
        if key in PEDAL:
            self._backup_once()
            return self._set_pedal(key, value)
        prm = P.BY_NAME.get(key)
        if prm is None:
            raise KeyError(f"the ToneX One has no setting {name!r}")
        if prm.blocked:
            raise KeyError(f"{prm.name} is not changed by ToneCommand: {prm.blocked}")
        opts = _options(prm)
        if isinstance(value, str):
            if not opts:
                raise KeyError(f"{prm.name} takes a number, not {value!r}")
            want = [i for i, o in enumerate(opts) if o.upper() == value.strip().upper()]
            if not want:
                raise KeyError(f"{prm.name} has no setting {value!r}; it has {', '.join(opts)}")
            value = want[0]
        value = float(value)
        if not prm.lo <= value <= prm.hi:
            raise ValueError(f"{prm.name} takes {prm.lo} to {prm.hi}, got {value}")
        self._backup_once()
        got = self.io.set_param(prm.index, value)
        label = opts[int(round(got))] if opts and 0 <= int(round(got)) < len(opts) else None
        return {"param": prm.name, "value": round(got, 3), "label": label}

    def _set_pedal(self, key: str, value: Any) -> dict:
        if key in ("SLOT_A", "SLOT_B", "SLOT_C"):
            idx = self._preset_index(value)
            st = self.io.write_state(**{key.lower(): idx})
            got = getattr(st, key.lower())
            return {"param": key, "value": got + 1, "label": self._label(got)}
        if key == "ACTIVE_SLOT":
            want = str(value).strip().upper()
            if want not in ACTIVE:
                raise KeyError("ACTIVE_SLOT is A, B or STOMP")
            fields = {"current_slot": ACTIVE.index(want)}
            # The stomp slot plays only in stomp mode, A and B only in dual.
            fields["stomp_mode"] = want == "STOMP"
            st = self.io.write_state(**fields)
            return {"param": key, "value": ACTIVE[min(st.current_slot, 2)], "label": None}
        if key == "MODE":
            want = str(value).strip().upper()
            if want not in ("DUAL", "STOMP"):
                raise KeyError("MODE is DUAL or STOMP")
            fields = {"stomp_mode": want == "STOMP",
                      "current_slot": 2 if want == "STOMP" else 0}
            st = self.io.write_state(**fields)
            return {"param": key, "value": "STOMP" if st.stomp_mode else "DUAL", "label": None}
        if key == "CAB_SIM":
            want = str(value).strip().upper()
            if want not in ("ON", "OFF"):
                raise KeyError("CAB_SIM is ON or OFF")
            st = self.io.write_state(cab_bypass=want == "OFF")
            return {"param": key, "value": "OFF" if st.cab_bypass else "ON", "label": None}
        if key == "INPUT_TRIM":
            st = self.io.write_state(input_trim=float(value))
            return {"param": key, "value": st.input_trim, "label": None}
        raise KeyError(key)

    def set_named_param(self, name: str, value: Any) -> dict:
        return self.set_param(name, value)

    def set_params_batch(self, items: Any) -> list:
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
        """Play preset `preset` (1..20): it goes into the slot now playing,
        which is what IK's own controllers do."""
        st = self.state()
        key = ("SLOT_A", "SLOT_B", "SLOT_C")[min(st.current_slot, 2)]
        return self.set_param(key, int(preset))

    # --- the slot list ------------------------------------------------------

    def slot_name(self, preset: int) -> str:
        return self.preset_names().get(int(preset) - 1, "")

    def is_slot_empty(self, preset: int) -> bool:
        return False

    def scan_slots(self, start: int = 1, end: int = p.PRESETS, **_):
        return [{"number": i, "name": self.slot_name(i), "empty": False}
                for i in range(start, min(end, p.PRESETS) + 1)]

    # --- declined -----------------------------------------------------------

    def _no(self, *a, **k):
        raise NotImplementedError("the ToneX One has no scenes, blocks or channels")

    set_scene = scene_name = set_bypass = set_channel = bulk_read = _no
    set_param_display = set_param_ordinal = get_param_display = _no

    def store_preset(self, slot: int):
        raise NotImplementedError("the ToneX One saves every change on its own; "
                                  "there is nothing to store")

    def close(self):
        self.io.close()
