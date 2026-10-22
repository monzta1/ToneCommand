"""A firmware-pinned Axe-Fx III registry, never an FM9 parameter fallback."""
from __future__ import annotations

from dataclasses import dataclass
import json
from importlib.resources import files

from fm9.registry import ParamSpec as BaseParamSpec, Registry as BaseRegistry
from .evidence import AXE_FX_III_PARAM_DEFINITIONS
from . import fw33_profile


SUPPORTED_FIRMWARE = frozenset({"32.06", fw33_profile.KEY})


@dataclass
class ParamSpec(BaseParamSpec):
    set_opcode: str = "09"
    verify_display_text: bool = True
    set_divisor: float | None = None
    wire_min: float | None = None
    display_tolerance: float | None = None
    firmware_versions: tuple[str, ...] = ()
    tempo_param_id: int | None = None


class Registry(BaseRegistry):
    """Reuse names/aliases, not the FM9 catalog or its write calibrations.

    Unsupported firmware has no writable specs or model roster. A catalog
    being present on disk never constitutes evidence for another firmware.
    """

    def __init__(self, firmware: str = ""):
        self.firmware = firmware
        self.model_byte = 0x10
        self.params = {}
        self.ranges = {}
        self.amp_roster = {}
        self.drive_roster = {}
        self.reverb_roster = {}
        self.cab_bank_names = {"0": "FACTORY 1", "1": "FACTORY 2", "2": "USER"}
        # Populated from device-specific catalogs or explicit user imports
        # later. Never label an AFX3 bank using the FM9 Legacy roster.
        self.cab_rosters = {}
        self.amp_models = {}
        self.drive_models = {}
        self.effect_type_models = {}
        self.cab_models = {}
        self.dynacabs = {}
        from .catalog import Catalog
        self.cab_catalog = Catalog(firmware)
        if firmware == fw33_profile.KEY:
            self.cab_bank_names = {'0':'FACTORY 1', '1':'FACTORY 2', '2':'USER 1',
                                   '3':'USER 2', '6':'USER 3 (FullRes)'}
        from .profile import apply
        apply(self, None)
        if firmware not in SUPPORTED_FIRMWARE:
            return
        self.definitions = (fw33_profile.definitions(AXE_FX_III_PARAM_DEFINITIONS)
                            if firmware == fw33_profile.KEY else AXE_FX_III_PARAM_DEFINITIONS)
        for family, definitions in self.definitions.items():
            for name, definition in definitions.items():
                self.params[family, definition["pid"]] = {
                    "name": name, "displayLabel": definition["label"],
                    "unit": definition["unit"], "family": family,
                    "paramId": definition["pid"],
                }
        data = json.loads(files("devices.axefx3").joinpath("data", "axe_fx_iii_amp_models.json").read_text(
            encoding="utf-8"))
        self.amp_roster = dict(data["firmware"]["32.06"]["models"])

    def spec(self, family: str, param_id: int, instance: int = 1) -> ParamSpec:
        if type(param_id) is not int or type(instance) is not int:
            raise ValueError("Parameter and instance addresses must be integers")
        entry = self.params.get((family, param_id))
        if entry is None:
            raise KeyError(f"No verified Axe-Fx III {self.firmware} parameter {family}/{param_id}")
        definition = self.definitions[family][entry["name"]]
        if self.firmware == fw33_profile.KEY and instance != 1:
            raise ValueError("Only measured first instances are supported on FW33")
        if family == "DISTORT" and instance not in (1, 2):
            raise ValueError("Axe-Fx III has Amp 1 and Amp 2 only")
        if family == "CHORUS" and instance != 1:
            raise ValueError("Only Chorus 1 has independent hardware evidence")
        if family in ('FUZZ','COMP','GEQ','PEQ') and instance != 1:
            raise ValueError('Only the first Drive/Compressor/EQ instance has hardware evidence')
        effect_id = self.effect_id(family, instance)
        return ParamSpec(
            family=family, instance=instance, effect_id=effect_id,
            param_id=param_id, name=entry["name"], label=definition["label"],
            unit=definition["unit"], kind=definition.get("kind", "float"),
            dmin=definition["min"], dmax=definition["max"],
            scale=definition.get("scale", "linear"),
            enum_count=definition.get("enum_count"),
            set_opcode=definition["set_opcode"], verify_display_text=True,
            set_divisor=definition.get("set_divisor"),
            wire_min=definition.get("wire_min"),
            display_tolerance=definition.get("display_tolerance"),
            firmware_versions=tuple(definition.get("firmware_versions", ())),
            tempo_param_id=definition.get("tempo_param_id"),
        )

    def validate_spec(self, spec: ParamSpec) -> None:
        """Reject forged addresses, encodings and ranges before any I/O."""
        if type(spec) is not ParamSpec:
            raise ValueError("An Axe-Fx III parameter specification is required")
        if self.firmware not in SUPPORTED_FIRMWARE:
            raise ValueError(f"Axe-Fx III firmware {self.firmware!r} is not verified")
        expected = self.spec(spec.family, spec.param_id, spec.instance)
        if spec != expected:
            raise ValueError("Parameter does not match the pinned Axe-Fx III reference")

    def selectable_amp_models(self) -> dict[str, str]:
        # Model ordinal zero needs separate evidence; do not reuse FM9's
        # alternate setter just because it works on that different unit.
        return {k: v for k, v in self.amp_roster.items() if k != "0"} if self.firmware == '32.06' else {}

    def effect_id(self, family: str, instance: int = 1) -> int:
        if family == 'NAM':
            if type(instance) is not int or instance != 1 or self.firmware != fw33_profile.KEY:
                raise ValueError('NAM requires the exact FW33 first-instance profile')
            return 206
        if type(instance) is not int or family == "GLOBAL":
            raise ValueError("Not a writable Axe-Fx III block address")
        if family == "DISTORT" and instance not in (1, 2):
            raise ValueError("Axe-Fx III has Amp 1 and Amp 2 only")
        if family == "CHORUS" and instance != 1:
            raise ValueError("Only Chorus 1 has independent hardware evidence")
        if (family in ('FUZZ','COMP','GEQ','PEQ') and instance != 1
                and not (family == 'PEQ' and instance == 2 and self.firmware == fw33_profile.KEY)):
            raise ValueError('Only the first Drive/Compressor/EQ instance has hardware evidence')
        return super().effect_id(family, instance)

    def family_of_effect_id(self, eid: int):
        if type(eid) is not int:
            return None
        if eid == 206 and self.firmware == fw33_profile.KEY:
            return ('NAM', 1)
        found = super().family_of_effect_id(eid)
        if found and (found[0] == "GLOBAL" or (found[0] == "DISTORT" and found[1] > 2)):
            return None
        return found

    def resolve_block(self, name: str, instance: int = 1):
        if name.strip().lower() in ('nam', 'nam player'):
            return 'NAM', self.effect_id('NAM', instance)
        return super().resolve_block(name, instance)

    def import_cab_names(self, text, kind, *, replace=False):
        count = self.cab_catalog.import_text(text, kind, replace=replace)
        self.cab_rosters = self.cab_catalog.rosters()
        return count

    def load_amp_facts(self, document):
        """Reuse upstream's facts by exact unique name, NEVER by FM9 ordinal.

        This does not expand the write roster or supply missing calibrations.
        The caller supplies the public facts document, not private guide prose.
        """
        if not isinstance(document, dict) or document.get("content") != "facts":
            raise ValueError("Expected the public facts-only amp sidecar")
        by_name = {}
        for record in document.get("amps", {}).values():
            by_name.setdefault(record.get("fractal"), []).append(record)
        fields = {"fractal", "model", "orig_cab", "dynacab", "controls",
                  "preamp_tubes", "power_tubes", "tonestack"}
        self.amp_models = {ordinal: {k: v for k, v in by_name[name][0].items() if k in fields}
                           for ordinal, name in self.amp_roster.items() if len(by_name.get(name, [])) == 1}
        return len(self.amp_models)
