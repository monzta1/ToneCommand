import json
from copy import deepcopy
from pathlib import Path

import pytest

from devices.axefx3.registry import Registry


def test_public_amp_facts_match_by_name_not_foreign_ordinals():
    reg = Registry("32.06")
    before = deepcopy(reg.params)
    document = {"content": "facts", "amps": {"999": {"fractal": reg.amp_roster["14"], "model": "Marshall",
                                                    "prose": "Do not import prose"}}}
    assert reg.load_amp_facts(document) == 1
    assert reg.amp_models == {"14": {"fractal": "Brit 800 2204 High", "model": "Marshall"}}
    assert reg.params == before


def test_ambiguous_names_are_not_guessed():
    reg = Registry("32.06")
    record = {"fractal": reg.amp_roster["14"], "model": "Unknown"}
    assert reg.load_amp_facts({"content": "facts", "amps": {"1": record, "2": record}}) == 0
    with pytest.raises(ValueError):
        reg.load_amp_facts({"content": "prose", "amps": {}})


def test_current_upstream_sidecar_enriches_330_pinned_names_without_new_writes():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config/amp_models.json").read_text(encoding="utf-8"))
    reg = Registry("32.06")
    before = deepcopy(reg.params)
    assert reg.load_amp_facts(data) == 330
    assert reg.params == before
