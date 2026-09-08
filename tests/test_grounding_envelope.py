"""The grounding sidecar envelope (#17, step 3).

These files are the highest-risk data in the repo: every fact is copied from
somewhere, none is measured here, and a wrong entry does not crash. It teaches
the planner a confident falsehood that reaches the player as advice. So the
envelope is what makes a sidecar reviewable, and these tests enforce it.
"""
from __future__ import annotations

import json

import pytest

from fm9 import grounding


def test_there_are_sidecars_to_check():
    """Guards the guard: a glob that silently matches nothing would make every
    test below pass while checking no file at all."""
    assert len(grounding.sidecars()) >= 4


@pytest.mark.parametrize("path", grounding.sidecars(), ids=lambda p: p.name)
def test_every_sidecar_carries_the_envelope(path):
    assert grounding.validate(path) == []


@pytest.mark.parametrize("path", grounding.sidecars(), ids=lambda p: p.name)
def test_every_sidecar_cites_a_checkable_source(path):
    """Facts-only grounding with citations is a non-negotiable of the epic.
    A reviewer has to be able to go and check an entry, which means the source
    names a document rather than gesturing at one."""
    src = json.loads(path.read_text())["source"]
    assert len(src) >= 12, f"{path.name}: {src!r} names nothing checkable"


@pytest.mark.parametrize("path", grounding.sidecars(), ids=lambda p: p.name)
def test_every_sidecar_says_what_its_keys_are(path):
    """Ordinal-keyed and name-keyed sidecars drift in different ways, and
    confusing the two is how a renumbered roster silently mislabels every
    entry. The file has to say which it is."""
    assert json.loads(path.read_text())["keyed_by"].strip()


# --- the validator has to actually reject things ------------------------

def _good(tmp_path, **over):
    blob = {k: "x" * 20 for k in grounding.ENVELOPE}
    blob["schema_version"] = 1
    blob["amps"] = {"0": {"fractal": "Euro Blue"}}
    blob.update(over)
    p = tmp_path / "thing_models.json"
    p.write_text(json.dumps(blob))
    return p


def test_the_validator_accepts_a_good_sidecar(tmp_path):
    assert grounding.validate(_good(tmp_path)) == []


@pytest.mark.parametrize("field", sorted(grounding.ENVELOPE))
def test_a_missing_envelope_field_is_rejected(tmp_path, field):
    p = _good(tmp_path)
    blob = json.loads(p.read_text())
    del blob[field]
    p.write_text(json.dumps(blob))
    assert any(field in m for m in grounding.validate(p))


def test_a_vague_citation_is_rejected(tmp_path):
    """'the wiki' is not provenance. It looks like a citation and cannot be
    used to check a single fact."""
    assert any("vague" in m for m in
               grounding.validate(_good(tmp_path, source="the wiki")))


def test_an_envelope_with_no_payload_is_rejected(tmp_path):
    blob = {k: "x" * 20 for k in grounding.ENVELOPE}
    blob["schema_version"] = 1
    p = tmp_path / "empty_models.json"
    p.write_text(json.dumps(blob))
    assert any("no payload" in m for m in grounding.validate(p))


def test_an_unreadable_sidecar_is_reported_not_raised(tmp_path):
    p = tmp_path / "broken_models.json"
    p.write_text("{ not json")
    assert grounding.validate(p) and "unreadable" in grounding.validate(p)[0]


# --- which files can be drift-guarded at all ----------------------------

def test_the_families_with_a_roster_are_the_ones_guarded():
    """registry.py refuses to load amp, drive and cab sidecars that disagree
    with the catalog roster. effect_type_models has no guard, and that is
    CORRECT rather than an oversight: the catalog carries no ordinal roster
    for delay, chorus, multitap or pitch types, so there is nothing to compare
    against until #5 maps them on hardware. Recorded here so the absence is
    known instead of being rediscovered and 'fixed' by inventing a roster.
    """
    import json as _json
    from pathlib import Path
    cat = _json.loads(
        (Path(grounding.CONFIG) / "fm9_catalog.json").read_text())["data"]
    rosters = {k for k in cat if "ROSTER" in k.upper()}
    assert {"FM9_AMP_ROSTER", "FM9_DRIVE_ROSTER",
            "FM9_CAB_ROSTERS_BY_BANK"} <= rosters
    assert not any("DELAY" in r or "CHORUS" in r or "MULTITAP" in r
                   for r in rosters), \
        "a type roster appeared; effect_type_models can now be drift-guarded"
    assert "effect_type_models" not in grounding.REQUIRES_DRIFT_GUARD


@pytest.mark.parametrize("family", sorted(grounding.REQUIRES_DRIFT_GUARD))
def test_a_guarded_family_really_refuses_a_drifted_sidecar(family, tmp_path,
                                                           monkeypatch):
    """The guard is the whole reason these files can be trusted, so prove it
    fires rather than assuming registry.py still calls it."""
    from fm9.registry import Registry
    reg = Registry()
    loader = {"amp_models": (reg._load_amp_models, "amps"),
              "drive_models": (reg._load_drive_models, "drives"),
              "cab_models": (reg._load_cab_models, "cabs")}[family]
    fn, key = loader
    blob = json.loads((grounding.CONFIG / f"{family}.json").read_text())
    # Corrupt one entry's recorded Fractal name: exactly what a renumbered
    # roster looks like from the sidecar's side.
    if family == "cab_models":
        bank = next(iter(blob[key]))
        slot = next(iter(blob[key][bank]))
        blob[key][bank][slot]["fractal"] = "NOT A REAL CAB"
    else:
        k = next(iter(blob[key]))
        blob[key][k]["fractal"] = "NOT A REAL MODEL"
    p = tmp_path / f"{family}.json"
    p.write_text(json.dumps(blob))
    with pytest.raises(Exception) as e:
        fn(p)
    assert "sync" in str(e.value).lower() or "stale" in type(e.value).__name__.lower()
