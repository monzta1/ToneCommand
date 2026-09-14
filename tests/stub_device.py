"""A second, structurally distinct implementation of the device contract.

Not a mock, and deliberately not an FM9. `SimFM9` is a factory that returns a
real `FM9` on simulated ports, so before #109 the contract had one
implementation reached by two routes and `conformance()` proved
self-consistency rather than portability -- which `fm9/adapter.py` has always
said in as many words.

This class inherits nothing, holds its state in dictionaries, and knows no
SysEx. What it is for is the shape of the contract, not the behaviour of any
device: it OPTS INTO some capability sub-Protocols and DECLINES others, so the
split is exercised rather than assumed, and it implements the tri-state
name-addressed scene model the FM9 cannot, so that shape is proven
implementable by something.

It stands in for the device @bschmalz81401 described on #33 closely enough to
stress the contract: names list without loading, per-slot scene state is
composable, and there is no editable 2D grid with cables.
"""
from __future__ import annotations

from fm9.adapter import Capabilities, ReadPath, SceneSlotState, Topology


class StubDevice:
    """A SELECTED-topology device, shaped like the HeadRush @bschmalz81401
    measured (#109): fourteen linear slots, no cables, and one integer that
    picks a whole prebuilt routing out of an enumerated list.

    Opts into ChainEditing, TopologySelection, Modifiers, Renaming and
    SceneSlots. Declines ChainWiring, because on a device that chooses from
    prebuilt routings there is nothing to connect, and FileInstall.
    """

    CAPABILITIES = Capabilities(
        read_path=ReadPath.DEVICE,
        observes_foreign_writes=True,     # a websocket reports changes we did not make
        reads_slot_names=True,            # names list without loading anything
        reads_slot_state=False,           # ...but the chain needs the rig loaded
        verifies_writes=True,
        has_scenes=True,
        stores_presets=True,
        topology=Topology.SELECTED,
        has_modifiers=True,
        installs_files=False,
        can_rename=True,
        composable_scene_slots=True,
    )

    def __init__(self, slots: dict[int, str] | None = None):
        self._slots = dict(slots or {0: "FIRST RIG", 1: "SECOND RIG"})
        self._preset = 0
        self._scene = 1
        self._scene_names = {1: "CLEAN", 2: "CRUNCH"}
        self._bypass: dict[int, bool] = {}
        self._channel: dict[int, int] = {}
        self._params: dict[tuple, float] = {}
        self._modifiers: dict[int, list[int]] = {}
        # Fourteen linear slots and ten routings, as the real device publishes
        # them. The NAMES are machine readable; their shapes are not, which is
        # exactly why SELECTED does not promise to describe one.
        self._chain: dict[int, int] = {}
        self._routings = ["S", "SPS-1", "SPS-2", "SPS-3", "PS-1",
                          "Vocal", "Dual", "Dual Vox-4", "Dual Vox-2",
                          "DualGuit"]
        self._routing = 0
        # scene -> slot NAME -> state. Absent is not the same as NO_CHANGE, and
        # that is the whole point of the tri-state.
        self._scene_slots: dict[int, dict[str, SceneSlotState]] = {}
        self.closed = False

    # --- DeviceAdapter ---------------------------------------------------

    def capabilities(self) -> Capabilities:
        return self.CAPABILITIES

    def status_dump(self):
        return {"preset": self._preset, "scene": self._scene,
                "bypass": dict(self._bypass), "channel": dict(self._channel)}

    def current_preset(self):
        return (self._preset, self._slots.get(self._preset, ""))

    def select_preset(self, preset: int):
        self._preset = int(preset)
        return self._preset

    def set_scene(self, scene_1based: int):
        self._scene = int(scene_1based)
        return self._scene

    def set_bypass(self, effect_id: int, bypassed: bool):
        self._bypass[effect_id] = bool(bypassed)
        return self._bypass[effect_id]

    def set_channel(self, effect_id: int, channel_0based: int):
        self._channel[effect_id] = int(channel_0based)
        return self._channel[effect_id]

    def set_param_display(self, spec, display_value: float):
        self._params[(getattr(spec, "effect_id", None),
                      getattr(spec, "param_id", None))] = float(display_value)
        return float(display_value)

    def set_param_ordinal(self, spec, ordinal: int):
        self._params[(getattr(spec, "effect_id", None),
                      getattr(spec, "param_id", None))] = int(ordinal)
        return int(ordinal)

    def get_param_display(self, spec):
        return self._params.get((getattr(spec, "effect_id", None),
                                 getattr(spec, "param_id", None)))

    def bulk_read(self, effect_id: int, timeout: float = 1.5):
        return []

    def slot_name(self, preset: int):
        return self._slots.get(int(preset))

    def scan_slots(self, start: int = 0, end: int = 511):
        for n in sorted(self._slots):
            if start <= n <= end:
                yield (n, self._slots[n])

    def is_slot_empty(self, preset: int):
        return int(preset) not in self._slots

    def set_params_batch(self, items):
        # Nothing to optimise here, so the contract's default shape applies:
        # loop, and report each one.
        return [self.set_param_display(spec, value) for spec, value in items]

    def scene_name(self, scene=None):
        n = self._scene if scene is None else int(scene)
        return (n, self._scene_names.get(n, ""))

    def firmware_label(self) -> str:
        # Its own vendor's convention, deliberately nothing like "12.00".
        return "5.1.0.2a63755"

    def store_preset(self, slot: int):
        self._slots[int(slot)] = self._slots.get(self._preset, "")
        return int(slot)

    def close(self):
        self.closed = True

    # --- ChainEditing ----------------------------------------------------

    def place_block(self, row_1based: int, col_1based: int, effect_id: int):
        # Position is opaque to the contract. Here it is a slot number, and
        # there is no second row to write.
        self._chain[int(col_1based)] = int(effect_id)
        return int(col_1based)

    def reorder_block(self, moving_eid: int, ref_eid: int):
        order = [s for s, e in sorted(self._chain.items())]
        return order

    # --- TopologySelection -----------------------------------------------

    def topologies(self):
        return list(self._routings)

    def current_topology(self):
        return (self._routing, self._routings[self._routing])

    def select_topology(self, index: int):
        self._routing = int(index)
        return self.current_topology()

    # --- Modifiers -------------------------------------------------------

    def bind_modifier(self, slot_1based: int, target_effect_id: int,
                      target_param_id: int, source_ordinal: int):
        self._modifiers[int(slot_1based)] = [target_effect_id, target_param_id,
                                             source_ordinal]
        return self._modifiers[int(slot_1based)]

    def read_modifier(self, slot_1based: int):
        return self._modifiers.get(int(slot_1based))

    def clear_modifier(self, slot_1based: int):
        self._modifiers.pop(int(slot_1based), None)

    # --- Renaming --------------------------------------------------------

    def rename_preset(self, name: str):
        self._slots[self._preset] = name
        return name

    def rename_scene(self, scene_1based: int, name: str):
        self._scene_names[int(scene_1based)] = name
        return name

    # --- SceneSlots ------------------------------------------------------

    def scene_slots(self, scene_1based: int):
        return dict(self._scene_slots.get(int(scene_1based), {}))

    def set_scene_slot(self, scene_1based: int, slot_name: str,
                       state: SceneSlotState):
        self._scene_slots.setdefault(int(scene_1based), {})[slot_name] = state
        return state
