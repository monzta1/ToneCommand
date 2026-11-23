"""#40: tools/fm3_settings_check.py drives the app's own FM3 code through
every measured setting and leaves the unit as it was."""
import importlib.util
from pathlib import Path

from fm9 import fm3_map
from fm9 import protocol as p
from fm9.registry import Registry
from fm9.sim import SimFM3

_root = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("fm3_settings_check", _root / "tools" / "fm3_settings_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)


def test_every_measured_setting_passes_on_the_simulator():
    reg = Registry()
    dev = SimFM3(reg)
    dev.settle_scale = 0.0
    lines = sc.run(dev, reg, say=lambda s: None)
    assert lines[-1] == "result: PASS", lines
    assert f"settings: {len(fm3_map.PARAMS)} passed, 0 failed, 0 skipped" in lines


def test_only_reads_and_measured_knob_writes_reach_the_fm3():
    reg = Registry()
    dev = SimFM3(reg)
    dev.settle_scale = 0.0
    sent = []
    real = dev.outp.port.send
    dev.outp.port.send = lambda m: (sent.append([0xF0, *m.data, 0xF7]) if m.type == "sysex" else None, real(m))
    sc.run(dev, reg, say=lambda s: None)
    for f in sent:
        assert p.fm3_allowed(f)
        if f[5] == p.FN_PARAM:
            eid, word = p.decode14(f[8], f[9]), p.decode14(f[10], f[11])
            assert word in fm3_map.WRITABLE_WORDS[eid]


def test_the_step_goes_toward_the_middle():
    m = fm3_map.lookup("REVERB", 0)
    assert sc._target(20.0, m) == 25.0 and sc._target(80.0, m) == 75.0


def test_settings_with_values_are_written_back_not_left_to_the_reload():
    reg = Registry()
    dev = SimFM3(reg)
    dev.settle_scale = 0.0
    for (family, _pid), m in fm3_map.PARAMS.items():
        dev.sim_core.st.buffer["params"][fm3_map.EFFECT_IDS[family]][0][m.word] = 30000
    lines = sc.run(dev, reg, say=lambda s: None)
    assert lines[-1] == "result: PASS", lines
    assert not any("restore by reload" in line for line in lines)
    assert sum("; restored " in line for line in lines) == len(fm3_map.PARAMS)
