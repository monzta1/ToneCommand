"""The IR-2 adapter against the contract and against the simulator.

The hardware facts these tests encode were all proven on Moncy's unit on
2026-09-29 and are recorded in kb/IR2_PROTOCOL.md. The two that matter most
are that a write is only true once it reads back, and that the pedal clamps
an out-of-range value instead of refusing it, which is exactly why the
adapter validates before sending.
"""
import pytest

from fm9.adapter import DeviceAdapter, ReadPath, Topology
from devices.ir2 import protocol as p
from devices.ir2 import registry as reg
from devices.ir2.adapter import IR2Adapter, INSTALL_REFUSED
from devices.ir2.client import VerifyFailed
from devices.ir2.sim import SimIR2


@pytest.fixture
def dev():
    return IR2Adapter(client=SimIR2())


# --- the contract ---------------------------------------------------------

def test_the_adapter_satisfies_the_device_contract(dev):
    assert isinstance(dev, DeviceAdapter)


def test_capabilities_are_declared_honestly(dev):
    c = dev.capabilities()
    # earned on hardware: reads matched the pedal's own pushes byte for byte
    assert c.read_path is ReadPath.DEVICE
    assert c.verifies_writes is True
    # the pedal announces knob turns without being asked, unlike the FM9
    assert c.observes_foreign_writes is True
    # declined, because the device genuinely has no such concept
    assert c.has_scenes is False
    assert c.has_modifiers is False
    assert c.installs_files is False
    assert c.topology is Topology.FIXED


def test_firmware_label_is_empty_because_the_unit_reports_zeros(dev):
    """The identity reply's revision field is all zeros on this pedal, so
    there is nothing honest to report. Empty, never invented."""
    assert dev.firmware_label() == ""


# --- reading --------------------------------------------------------------

def test_patch_reads_every_knob_by_name(dev):
    patch = dev.patch()
    assert set(patch) == {"BASS", "MIDDLE", "TREBLE", "LEVEL", "GAIN",
                          "AMBIENCE", "AMP"}
    assert patch["AMP"] == "CLEAN"


def test_system_block_decodes_the_nibble_pair_fields(dev):
    """USB levels are INTEGER2x4, one value across two 4-bit nibbles. The
    unit read 06 04 for each, which is 100, and 100 is their documented
    default. A byte-per-field reading would have said 6."""
    sysm = dev.system()
    assert sysm["USB_OUT_LEVEL"] == 100
    assert sysm["USB_IN_LEVEL"] == 100
    assert sysm["USB_LOOPBACK_LEVEL"] == 100
    assert sysm["AMP_CAB_SW"] == "AMP ON / CAB ON"


def test_status_dump_names_the_device_and_carries_both_blocks(dev):
    d = dev.status_dump()
    assert d["device"] == "ir2"
    assert "AMP" in d["patch"] and "USB_MODE" in d["system"]


# --- writing, and the verification that makes it true ---------------------

def test_set_amp_by_name_reports_what_the_unit_says(dev):
    r = dev.set_amp("BROWN")
    assert r["value"] == 8 and r["label"] == "BROWN"
    assert dev.patch()["AMP"] == "BROWN"


def test_every_amp_name_round_trips(dev):
    for i, name in enumerate(reg.AMP_NAMES):
        assert dev.set_amp(name)["value"] == i
        assert dev.patch()["AMP"] == name


def test_an_amp_the_pedal_does_not_have_is_refused_before_anything_is_sent(dev):
    with pytest.raises(KeyError, match="PLEXI"):
        dev.set_amp("PLEXI")
    assert dev.io.writes == []


def test_out_of_range_is_refused_here_because_the_pedal_clamps_silently(dev):
    """Writing 0x0B to AMP made the unit report 0x0A. A clamp that reached
    the wire would be reported as a successful write by read-back, so the
    range check has to happen before the send, not after."""
    with pytest.raises(ValueError, match="0 to 10"):
        dev.set_param("AMP", 11)
    assert dev.io.writes == []


def test_a_write_that_does_not_read_back_raises_rather_than_reporting_success():
    class Liar(SimIR2):
        def write(self, addr, data, verify=True):
            super().write(addr, data, verify=False)
            self.blocks[p.PATCH][6] = 0        # the unit did something else
            if verify:
                raise VerifyFailed("read-back disagreed")
            return data

    dev = IR2Adapter(client=Liar())
    with pytest.raises(VerifyFailed):
        dev.set_amp("RFIER")


def test_continuous_params_take_the_full_wire_range(dev):
    for name in ("BASS", "MIDDLE", "TREBLE", "LEVEL", "GAIN", "AMBIENCE"):
        assert dev.set_param(name, 127)["value"] == 127
        assert dev.set_param(name, 0)["value"] == 0
        with pytest.raises(ValueError):
            dev.set_param(name, 128)


def test_batch_names_the_item_that_failed_rather_than_reporting_a_partial_run(dev):
    with pytest.raises(ValueError, match=r"item 1 \(AMP\)"):
        dev.set_params_batch([{"name": "BASS", "value": 10},
                              {"name": "AMP", "value": 99}])


def test_select_preset_switches_the_two_stored_patches(dev):
    assert dev.select_preset(1)["value"] == 1
    assert dev.current_preset()[0] == 1
    with pytest.raises(ValueError):
        dev.select_preset(2)


# --- what the player does on the pedal -----------------------------------

def test_a_knob_the_player_turns_is_observed_without_polling(dev):
    dev.io.push(p.PATCH + 4, [99])           # the pedal announces GAIN
    assert dev.observed_changes() == [{"param": "GAIN", "value": 99}]
    assert dev.observed_changes() == []      # drained, not repeated


def test_a_footswitch_press_is_observed_as_the_patch_number(dev):
    dev.io.push(p.SETUP, [1])
    assert dev.observed_changes() == [{"param": "PATCH_NUMBER", "value": 1}]


# --- IR slots: listed, never written -------------------------------------

def test_the_eleven_user_slots_are_listed_as_the_pedal_numbers_them(dev):
    rows = dev.list_captures()
    assert [c.slot for c in rows] == list(range(1, 12))
    assert len(rows) == p.IR_SLOTS == 11


def test_installing_an_ir_refuses_in_one_line_and_sends_nothing(dev):
    with pytest.raises(NotImplementedError) as e:
        dev.install_capture(None, b"\x00" * 16, 0)
    assert "invariant 0" in str(e.value)
    assert dev.io.writes == []


def test_removing_an_ir_refuses_the_same_way(dev):
    with pytest.raises(NotImplementedError, match="invariant 0"):
        dev.remove_capture(3)


def test_slot_lookups_use_the_pedals_numbering(dev):
    """slot_name(1) is USER 1, not the second row of a zero-based list."""
    assert dev.slot_name(1) == ""            # empty on the simulator
    assert dev.is_slot_empty(11) is True
    with pytest.raises(KeyError, match="not 0"):
        dev.slot_name(0)
    assert [r["slot"] for r in dev.scan_slots()] == list(range(1, 12))


def test_the_capture_whitelist_is_empty_so_nothing_is_writable_by_declaration(dev):
    assert dev.capture_capabilities().whitelist == frozenset()
    assert dev.capture_capabilities().slots == p.IR_SLOTS == 11


# --- concepts this device does not have, stated rather than faked --------

@pytest.mark.parametrize("call,match", [
    (lambda d: d.set_scene(1), "no scenes"),
    (lambda d: d.scene_name(), "no scenes"),
    (lambda d: d.set_bypass(106, True), "no effect blocks"),
    (lambda d: d.set_channel(106, 0), "no effect blocks"),
    (lambda d: d.bulk_read(106), "no effect blocks"),
    (lambda d: d.store_preset(1), "not decoded"),
    (lambda d: d.set_param_display(None, 1.0), "does not publish the curve"),
    (lambda d: d.get_param_display(None), "does not publish its taper"),
])
def test_absent_concepts_refuse_in_one_line(dev, call, match):
    with pytest.raises(NotImplementedError, match=match):
        call(dev)


def test_the_registry_refuses_to_invent_a_taper():
    with pytest.raises(reg.NotMeasured, match="does not publish the curve"):
        reg.resolve("BASS").to_display(64)


def test_every_amp_carries_the_vendors_own_cab_file_name():
    assert len(reg.AMPS) == 11
    for name, cab in reg.AMPS:
        assert cab.endswith(".wav") and name.isupper()


# --- the device kind ------------------------------------------------------

def test_the_picker_offers_the_ir2_when_the_pedal_is_plugged_in(monkeypatch):
    """No environment variable needed: plugging the pedal in is the whole
    setup. tests/conftest.py turns the probe off for every other test, so
    this is the one place hardware presence is allowed to matter."""
    import server
    monkeypatch.delenv("TONECOMMAND_IR2_SIM", raising=False)
    monkeypatch.delenv("TONECOMMAND_TONEX_SIM", raising=False)
    monkeypatch.delenv("TONECOMMAND_TONEX_PORT", raising=False)
    monkeypatch.delenv("TONECOMMAND_HEADRUSH_SIM", raising=False)
    monkeypatch.delenv("TONECOMMAND_HEADRUSH_HOST", raising=False)

    monkeypatch.setattr(server, "_ir2_port_present", lambda: False)
    assert [d["kind"] for d in server.available_devices()] == ["fm9"]

    monkeypatch.setattr(server, "_ir2_port_present", lambda: True)
    assert {"kind": "ir2", "label": "BOSS IR-2"} in server.available_devices()


def test_a_broken_midi_binding_means_no_ir2_not_a_failed_device_list(monkeypatch):
    """Device discovery runs on every poll of the header. It must never be
    the thing that breaks the page."""
    import server
    monkeypatch.setattr(server, "_ir2_port_present",
                        server._ir2_port_present.__wrapped__
                        if hasattr(server._ir2_port_present, "__wrapped__")
                        else server._ir2_port_present)
    import builtins
    real_import = builtins.__import__

    def boom(name, *a, **k):
        if name == "rtmidi":
            raise ImportError("no binding here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    assert server._ir2_port_present() is False


def test_the_sim_backed_context_builds_and_registers(monkeypatch):
    import server
    monkeypatch.setenv("TONECOMMAND_IR2_SIM", "1")
    ctx = server._build_context("ir2")
    assert ctx.kind == "ir2" and ctx.label == "BOSS IR-2"
    assert ctx.adapter.capabilities().observes_foreign_writes is True
    assert len(ctx.adapter.list_captures()) == p.IR_SLOTS
    assert ctx.adapter.patch()["AMP"] == "CLEAN"


def test_the_device_endpoint_lists_the_ir2(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    monkeypatch.setenv("TONECOMMAND_IR2_SIM", "1")
    monkeypatch.setattr(server, "_context", server._default_context)
    r = TestClient(server.app).get("/api/device").json()
    assert any(d["kind"] == "ir2" for d in r["available"])
