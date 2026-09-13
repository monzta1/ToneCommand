"""Versioned, hardware-independent policies for offline sound measurements.

This module deliberately contains no device or action-runner imports.  Policies
describe comparisons; they never authorize a write to an FM9.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping


POLICY_VERSION = "sound-policy/1.0"


@dataclass(frozen=True)
class SceneLoudnessPolicy:
    """Explicit relationships used for a scene-to-rhythm comparison."""

    policy_id: str = "scene-balance-default"
    version: str = POLICY_VERSION
    lead_target_lu: tuple[float, float] = (2.0, 3.0)
    lead_concern_above_lu: float = 4.0
    clean_target_lu: tuple[float, float] | None = None

    def target_for_role(self, role: str) -> tuple[float, float] | None:
        role = role.strip().lower()
        if role == "rhythm":
            return (0.0, 0.0)
        if role == "lead":
            return self.lead_target_lu
        if role == "clean":
            return self.clean_target_lu
        return None


def evaluate_band_policy(
    band_db: Mapping[str, float],
    limits: Mapping[str, Mapping[str, float]],
) -> list[dict[str, object]]:
    """Evaluate only explicitly supplied band limits.

    A limit may contain ``min_db`` and/or ``max_db``.  Absence of a limit is
    not interpreted as a pass; callers report that missing policy separately.
    """

    findings: list[dict[str, object]] = []
    for band, rule in limits.items():
        if band not in band_db:
            continue
        value = float(band_db[band])
        if not math.isfinite(value):
            continue
        minimum = rule.get("min_db")
        maximum = rule.get("max_db")
        if minimum is not None and math.isfinite(float(minimum)) and value < float(minimum):
            findings.append(
                {"band": band, "direction": "below", "value_db": value, "limit_db": float(minimum)}
            )
        if maximum is not None and math.isfinite(float(maximum)) and value > float(maximum):
            findings.append(
                {"band": band, "direction": "above", "value_db": value, "limit_db": float(maximum)}
            )
    return findings
