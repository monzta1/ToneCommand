"""CabTarget: the minimal resolved cab intent a plan carries, post-plan.

Brief section 9 defines a much larger contract (schema version, provenance,
five target kinds, named-tone hypothesis resolution). None of that lives
here. This is only the slice the eighth-defect fix (19.5, 26.5) needs: the
planner's gear translation, the player's own words, and whether Current's
identity is a hard constraint on the search. matcher.parse()'s richer
structure (axes, reject sets, preserve_intent, unresolved) stays inside
IRCommand, reusable later as a validation step; reproducing it here would be
building that larger, separately-scoped contract under a different name.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CabTarget:
    """What one plan asks of the cab library, resolved once and read by the
    one post-plan selector (`cab_listening_set`), whichever branch of
    `_plan_for` built the plan.
    """

    gear: str | None
    request: str
    whole_rig: bool
    preserve: str | None

    @property
    def readable(self) -> bool:
        """False for a null/blank `cab_need`: the plan said nothing about
        the cab, so there is nothing to search for."""
        return bool(self.gear)

    @classmethod
    def from_plan(cls, result: dict, anchor: dict) -> "CabTarget":
        """Resolve from a finished plan and the rig's Current anchor.

        The SAME resolution for the shared-profile and live branches of
        `_plan_for`, so a gear-anchored preserve constraint cannot drift
        between the two (brief 19.5, 26.5): both call this with their own
        anchor and get identical rules applied.
        """
        gear = (result.get("cab_need") or "").strip() or None
        whole_rig = bool(result.get("whole_rig"))
        # THE PLAYER'S WORDS DECIDE, and only the player's. This used to send
        # the prompt, the model's summary and the model's cab_need as one
        # blob, so a summary that happened to contain "similar" turned
        # preservation on for a player who never asked for it.
        request = str(result.get("request") or result.get("prompt") or "")

        preserve = None
        # Preserve Current's character ONLY when the player asked to keep
        # it. Forcing it otherwise is self-contradictory: a build asking for
        # a 4x12 V30 while the loaded cab is a 1x4 Pignose would have every
        # candidate excluded for not being a Pignose. Whole-rig builds never
        # preserve, by definition.
        if anchor.get("state") in ("gear_anchored", "measured") and not whole_rig:
            # A MEASURED Current gets this too. Curve proximity is not the
            # same promise as keeping the cabinet: the nearest curve in the
            # library can be a different size with a different speaker, and
            # "keep the same character" is a claim about the gear, not about
            # a distance. Only fields that are GEAR. `name` is not: for a
            # factory slot it is the roster label plus bank noise, and for a
            # user slot it is free text the player typed. Falling through to
            # it turned a label into a hard retrieval constraint (brief
            # 26.1). No gear means no preserve.
            preserve = (anchor.get("gear") or anchor.get("fractal")
                        or anchor.get("models"))
        return cls(gear=gear, request=request, whole_rig=whole_rig,
                   preserve=preserve)
