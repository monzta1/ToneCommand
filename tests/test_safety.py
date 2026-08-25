"""Invariant 0 is architecture, not policy: prove it holds off the FM9 too.

The guard used to be a check inside FM9._send, so it protected exactly one
device. These tests pin the property that actually matters: a transport that
declares nothing can send nothing, and the FM9's own behaviour is unchanged
by the lift.
"""
import pytest

from fm9 import safety
from fm9.device import FM9


def test_a_declared_kind_passes():
    guard = safety.sysex_guard("FM9", {0x01, 0x08})
    guard.check(0x01)
    assert guard.permits(0x08)


def test_an_undeclared_kind_is_refused():
    guard = safety.sysex_guard("FM9", {0x01})
    with pytest.raises(safety.BrickGuardRefusal) as err:
        guard.check(0x7F)
    assert "0x7f" in str(err.value)
    assert "invariant 0" in str(err.value)


def test_the_refusal_is_still_a_permission_error():
    """Callers that predate the lift catch PermissionError."""
    assert issubclass(safety.BrickGuardRefusal, PermissionError)


def test_an_undeclared_transport_can_send_nothing():
    """The whole point of the lift. A new adapter that forgets to declare an
    allowlist fails closed, so the unsafe state has to be opted into."""
    for kind in (0x01, 0x08, "sysex", "program_change", None):
        with pytest.raises(safety.BrickGuardRefusal):
            safety.DENY_ALL.check(kind)


def test_the_fm9_allowlist_is_unchanged_by_the_lift():
    expected = {0x01, 0x08, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x13, 0x14, 0x1F}
    assert set(FM9.SENDABLE_FNS) == expected
    assert FM9.guard.permits(0x01)


@pytest.mark.parametrize("fn", [0x02, 0x03, 0x7F, 0x00, 0x21])
def test_the_fm9_still_refuses_undecoded_functions(fn):
    assert fn not in FM9.SENDABLE_FNS
    with pytest.raises(PermissionError):
        FM9.guard.check(fn)


def test_a_message_type_device_refuses_sysex():
    """ToneX shape. SysEx is where firmware traffic lives on an undecoded
    device, so it must not be reachable even when MIDI itself is."""
    guard = safety.message_type_guard("ToneX",
                                      ("program_change", "control_change"))
    guard.check("program_change")
    guard.check("control_change")
    for kind in ("sysex", "sysex_end", "reset", "songpos"):
        with pytest.raises(safety.BrickGuardRefusal):
            guard.check(kind)


def test_the_tonex_probe_uses_the_shared_guard():
    """Not a private reimplementation: device two inherits invariant 0."""
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parent.parent / "tools" / "tonex_probe.py"
    spec = importlib.util.spec_from_file_location("tonex_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert isinstance(mod.GUARD, safety.SendGuard)
    assert mod.GUARD.permits("program_change")
    assert not mod.GUARD.permits("sysex")
