"""Firmware-pinned FM9 block and parameter registry.

Loads config/fm9_catalog.json (device-true param catalog mined by
mcp-midi-control, Apache-2.0) and maps friendly block/param names onto
(effect_id, param_id, display range, scale).

Firmware: catalog mined against FM9 11.x; parameter get/set re-verified on
12.00 (test_phase2.py, 2026-08-19). After any firmware update, re-verify the
editor protocol paths (fn 0x01) before trusting writes.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG = Path(__file__).resolve().parent.parent / "config" / "fm9_catalog.json"
AMP_MODELS = Path(__file__).resolve().parent.parent / "config" / "amp_models.json"

# v1.4 PDF Appendix 1: family -> effect ID of instance 1 (instances contiguous)
EFFECT_ID_BASE = {
    "INPUT": (37, 5), "OUTPUT": (42, 4), "COMP": (46, 4), "GEQ": (50, 4),
    "PEQ": (54, 4), "DISTORT": (58, 4), "CABINET": (62, 4), "REVERB": (66, 4),
    "DELAY": (70, 4), "MULTITAP": (74, 4), "CHORUS": (78, 4), "FLANGER": (82, 4),
    "ROTARY": (86, 4), "PHASER": (90, 4), "WAH": (94, 4), "FORMANT": (98, 4),
    "VOLUME": (102, 4), "TREMOLO": (106, 4), "PITCH": (110, 4), "FILTER": (114, 4),
    "FUZZ": (118, 4), "ENHANCER": (122, 4), "MIXER": (126, 4), "SYNTH": (130, 4),
    "VOCODER": (134, 4), "MEGATAP": (138, 4), "CROSSOVER": (142, 4),
    "GATE": (146, 4), "RINGMOD": (150, 4), "MULTICOMP": (154, 4),
    "TENTAP": (158, 4), "RESONATOR": (162, 4), "LOOPER": (166, 4),
    "TONEMATCH": (170, 4), "RTA": (174, 4), "PLEX": (178, 4),
    "FDBKSEND": (182, 4), "FDBKRET": (186, 4), "MIDIBLOCK": (190, 1),
    "MULTIPLEXER": (191, 4), "IRPLAYER": (195, 4),
}

# user-facing block names -> catalog family
BLOCK_ALIASES = {
    "amp": "DISTORT", "amplifier": "DISTORT", "distort": "DISTORT",
    "cab": "CABINET", "cabinet": "CABINET",
    "drive": "FUZZ", "fuzz": "FUZZ", "pedal": "FUZZ",
    "gate": "GATE", "noise gate": "GATE", "noisegate": "GATE",
    "input": "INPUT", "input gate": "INPUT",
    "output": "OUTPUT",
    "comp": "COMP", "compressor": "COMP",
    "geq": "GEQ", "graphic eq": "GEQ", "graphiceq": "GEQ",
    "peq": "PEQ", "parametric eq": "PEQ", "parametriceq": "PEQ", "eq": "PEQ",
    "reverb": "REVERB", "delay": "DELAY", "chorus": "CHORUS",
    "flanger": "FLANGER", "rotary": "ROTARY", "phaser": "PHASER",
    "wah": "WAH", "volume": "VOLUME", "tremolo": "TREMOLO",
    "pitch": "PITCH", "filter": "FILTER", "looper": "LOOPER",
    "plex": "PLEX", "multitap": "MULTITAP",
}

# Frequency-flavoured typecodes observed to be log10-tapered on this family
# (cab/PEQ low-cut and high-cut anchors, mcp-midi-control hardware evidence).
LOG10_TYPECODES = {578, 579, 1090, 1091}


@dataclass
class ParamSpec:
    family: str
    instance: int          # 1-based
    effect_id: int
    param_id: int
    name: str              # e.g. DISTORT_DRIVE
    label: str | None      # e.g. "Gain"
    unit: str | None
    kind: str              # "float" | "enum" | "unknown"
    dmin: float | None
    dmax: float | None
    scale: str             # "linear" | "log10"
    enum_count: int | None


class AmpModelsStale(RuntimeError):
    """config/amp_models.json describes a roster that no longer matches."""


class Registry:
    def __init__(self, config_path: Path = CONFIG,
                 amp_models_path: Path = AMP_MODELS):
        raw = json.loads(config_path.read_text())
        data = raw["data"]
        self.model_byte = int(raw["model_byte"], 16)
        self.params: dict[tuple[str, int], dict] = {
            (p["family"], p["paramId"]): p for p in data["FM9_PARAMS"]
        }
        self.ranges: dict[str, dict] = data["FM9_RANGES"]
        self.amp_roster: dict = data.get("FM9_AMP_ROSTER", {})
        self.drive_roster: dict = data.get("FM9_DRIVE_ROSTER", {})
        self.reverb_roster: dict = data.get("FM9_REVERB_TYPE_ROSTER", {})
        self.amp_models: dict = self._load_amp_models(amp_models_path)

    def _load_amp_models(self, path: Path) -> dict:
        """Load the real-world amp sidecar, refusing it if the roster moved.

        Each record carries a copy of the Fractal name it was built against. A
        catalog refresh that renumbers ordinals would otherwise silently
        mislabel every amp, which is invisible at runtime and poisons planning.
        """
        if not path.exists():
            return {}                      # optional sidecar; core still works
        amps = json.loads(path.read_text()).get("amps", {})
        drift = [f"{k}: sidecar {v.get('fractal')!r} != roster "
                 f"{self.amp_roster.get(k)!r}"
                 for k, v in amps.items() if self.amp_roster.get(k) != v.get("fractal")]
        if drift:
            raise AmpModelsStale(
                f"{path.name} is out of sync with the catalog amp roster "
                f"({len(drift)} of {len(amps)} entries). Regenerate it with "
                f"tools/build_amp_models.py. First mismatches: " + "; ".join(drift[:3]))
        return amps

    def amp_model(self, ordinal: int | str) -> str | None:
        """Real-world amp modeled by a roster ordinal, if known."""
        return self.amp_models.get(str(ordinal), {}).get("model")

    def amp_description(self, ordinal: int | str) -> str:
        """Fractal name annotated with the modeled amp, e.g.
        'Brit 800 2204 High = 50W Marshall JCM800 2204, High sensitivity in'."""
        name = self.amp_roster.get(str(ordinal), str(ordinal))
        model = self.amp_model(ordinal)
        return f"{name} = {model}" if model else name

    def effect_id(self, family: str, instance: int = 1) -> int:
        base, count = EFFECT_ID_BASE[family]
        if not 1 <= instance <= count:
            raise ValueError(f"{family} instance must be 1..{count}")
        return base + instance - 1

    def family_of_effect_id(self, eid: int) -> tuple[str, int] | None:
        for fam, (base, count) in EFFECT_ID_BASE.items():
            if base <= eid < base + count:
                return (fam, eid - base + 1)
        return None

    def resolve_block(self, name: str, instance: int = 1) -> tuple[str, int]:
        fam = BLOCK_ALIASES.get(name.strip().lower())
        if fam is None:
            if name.strip().upper() in EFFECT_ID_BASE:
                fam = name.strip().upper()
            else:
                raise KeyError(f"unknown block: {name}")
        return (fam, self.effect_id(fam, instance))

    def spec(self, family: str, param_id: int, instance: int = 1) -> ParamSpec:
        p = self.params.get((family, param_id), {})
        r = self.ranges.get(family, {}).get(str(param_id), {})
        kind = r.get("kind", "unknown")
        typecode = r.get("typecode", 0)
        scale = "log10" if typecode in LOG10_TYPECODES else "linear"
        dmin, dmax = r.get("displayMin"), r.get("displayMax")
        if dmin is not None and dmax is not None and dmin >= dmax:
            dmin = dmax = None  # uncalibrated row
        if scale == "log10" and (not dmin or dmin <= 0):
            scale = "linear"
        return ParamSpec(
            family=family, instance=instance,
            effect_id=self.effect_id(family, instance),
            param_id=param_id,
            name=p.get("name", f"{family}_{param_id}"),
            label=p.get("displayLabel"), unit=p.get("unit"),
            kind=kind, dmin=dmin, dmax=dmax, scale=scale,
            enum_count=r.get("enumCount"),
        )

    def find_param(self, family: str, needle: str) -> ParamSpec | None:
        """Look up a param in a family by symbolic name or display label."""
        needle_l = needle.strip().lower().replace(" ", "")
        for (fam, pid), p in self.params.items():
            if fam != family:
                continue
            name = (p.get("name") or "").lower()
            label = (p.get("displayLabel") or "").lower().replace(" ", "")
            if needle_l == label or name.endswith("_" + needle_l) or name == needle_l:
                return self.spec(fam, pid)
        return None
