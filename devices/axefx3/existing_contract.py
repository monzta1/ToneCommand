"""Pure scene-aware scalar proposal contract, not an executor or a writer.

The host supplies independently qualified controls and complete observations.
AI output cannot extend that surface. No device, provider, transport or route
is imported here. Successful validation is never permission to SEND.
"""
from copy import deepcopy
import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator


Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]
Channel = Literal['A', 'B', 'C', 'D']
Text = Annotated[str, Field(strict=True, min_length=3, max_length=600)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Change(StrictModel):
    effect_id: Annotated[StrictInt, Field(ge=1, le=207)]
    channel: Channel
    parameter: Annotated[str, Field(strict=True, min_length=2, max_length=80)]
    value: Number
    reason: Text


class Goal(StrictModel):
    scene: Annotated[StrictInt, Field(ge=1, le=8)]
    target: Text


class Design(StrictModel):
    summary: Annotated[str, Field(strict=True, min_length=3, max_length=5000)]
    changes: Annotated[list[Change], Field(min_length=1, max_length=160)]
    scene_goals: Annotated[list[Goal], Field(min_length=8, max_length=8)]


class Block(StrictModel):
    effect_id: Annotated[StrictInt, Field(ge=1, le=207)]
    channel: Channel
    bypassed: StrictBool


class Scene(StrictModel):
    scene: Annotated[StrictInt, Field(ge=1, le=8)]
    name: Annotated[str, Field(strict=True, max_length=31)]
    blocks: Annotated[list[Block], Field(min_length=1, max_length=207)]

    @model_validator(mode='after')
    def unique_blocks(self):
        ids = [b.effect_id for b in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate block in scene observation')
        return self


class Parameter(StrictModel):
    """Host metadata, never part of the AI Design schema or a write permit.

    Qualification, ownership and timing/wet-only interpretation must come
    from independently verified host code. False is the qualification default.
    """
    effect_id: Annotated[StrictInt, Field(ge=1, le=207)]
    channel: Channel
    parameter: Annotated[str, Field(strict=True, min_length=2, max_length=80)]
    param_id: Annotated[StrictInt, Field(ge=0, le=16383)]
    model: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    current: Number
    minimum: Number
    maximum: Number
    tolerance: Annotated[Number, Field(ge=0)]
    qualified: StrictBool = False
    modifier_owned: StrictBool = False
    timing_linked: StrictBool = False
    wet_only: StrictBool = False

    @model_validator(mode='after')
    def coherent_range(self):
        if self.minimum >= self.maximum:
            raise ValueError('Non-empty qualified range required')
        if self.tolerance >= self.maximum - self.minimum:
            raise ValueError('Tolerance cannot swallow the entire parameter range')
        # Current can be outside a new-build bound. Do not silently normalize it.
        return self


class Context(StrictModel):
    declared_chassis: Literal['mk1', 'mk2', 'turbo']
    preset: Annotated[StrictInt, Field(ge=0, le=1023)]
    name: Annotated[str, Field(strict=True, max_length=31)]
    scene: Annotated[StrictInt, Field(ge=1, le=8)]
    observed_state: dict[str, Any]
    scene_maps: Annotated[list[Scene], Field(min_length=8, max_length=8)]
    editable_parameters: Annotated[list[Parameter], Field(max_length=1024)]

    @model_validator(mode='after')
    def coherent_observations(self):
        if self.declared_chassis == 'mk1' and self.preset >= 512:
            raise ValueError('Declared Mark I capacity is 512 presets')
        if [m.scene for m in self.scene_maps] != list(range(1, 9)):
            raise ValueError('Observe all eight original scene maps in order')
        inventories = [{b.effect_id for b in m.blocks} for m in self.scene_maps]
        if any(ids != inventories[0] for ids in inventories):
            raise ValueError('Block inventory changed between scene observations')
        keys = [_key(p) for p in self.editable_parameters]
        addresses = [(p.effect_id, p.channel, p.param_id) for p in self.editable_parameters]
        if len(keys) != len(set(keys)) or len(addresses) != len(set(addresses)):
            raise ValueError('Duplicate editable parameter or aliased address')
        if not self.observed_state:
            raise ValueError('Do not invent an empty preservation baseline')
        _canonical(self.observed_state)  # Reject non-JSON and non-finite observations.
        return self


def _key(value):
    return value.effect_id, value.channel, value.parameter


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _impact(parameter, scenes):
    affected, active = [], []
    for scene in scenes:
        matching = [b for b in scene.blocks if b.effect_id == parameter.effect_id
                    and b.channel == parameter.channel]
        if matching:
            affected.append(scene.scene)
            if not matching[0].bypassed:
                active.append(scene.scene)
    return affected, active


def compile_design(raw, context):
    """Return a detached review-only delta; never raw generic executor actions.

    The caller must validate that observed_state is an actual complete, stable
    device snapshot and scene_maps came from its muted survey. This pure layer
    cannot prove hardware provenance, freshness, firmware or chassis identity.
    """
    ctx = Context.model_validate(context)
    design = Design.model_validate(raw)
    if [g.scene for g in design.scene_goals] != list(range(1, 9)):
        raise ValueError('Explain all eight scene goals in order')
    available = {_key(p): p for p in ctx.editable_parameters}
    seen, covered, changes = set(), set(), []
    for change in design.changes:
        key = _key(change)
        if key in seen or key not in available:
            raise ValueError('Repeated, absent or unqualified parameter')
        seen.add(key)
        p = available[key]
        if (not p.qualified or p.modifier_owned or p.timing_linked or p.wet_only
                or p.effect_id in {*range(37, 46), 200, 201}
                or p.parameter in ('DISTORT_LEVEL', 'WAH_CONTROL', 'VOLUME_CONTROL',
                                   'PITCH_CONTROL', 'OUTPUT_LEVEL', 'TYPE')):
            raise ValueError('Unqualified or preserved parameter is not editable')
        if not p.minimum <= change.value <= p.maximum:
            raise ValueError('Requested value outside the qualified range; no clamp')
        if abs(p.current - change.value) <= p.tolerance:
            raise ValueError('Identical or rounding-only settings are not changes')
        affected, active = _impact(p, ctx.scene_maps)
        if not affected:
            raise ValueError('Parameter channel is not used by an observed scene')
        covered.update(active)
        changes.append(dict(effect_id=p.effect_id, channel=p.channel,
            parameter=p.parameter, param_id=p.param_id, model=p.model,
            before=p.current, after=change.value, reason=change.reason,
            affected_scenes=affected, active_scenes=active))
    if covered != set(range(1, 9)):
        raise ValueError('Every scene needs an actual change to an active qualified block')
    baseline = ctx.model_dump()
    return deepcopy(dict(mode='existing_scalar_proposal', summary=design.summary,
        target=dict(preset=ctx.preset, name=ctx.name, scene=ctx.scene,
                    declared_chassis=ctx.declared_chassis),
        baseline_digest=hashlib.sha256(_canonical(baseline).encode()).hexdigest(),
        scene_goals=design.model_dump()['scene_goals'], changes=changes,
        preserved=['Grid and connections', 'Block inventory, models and cabinets',
                   'Scene names, channel assignments and bypass states',
                   'Modifiers, Input, Output and Amp Level', 'All unproposed parameter words'],
        executable=False, stored=False,
        warnings=['Shared-channel changes affect every listed scene.',
                  'This is a planning contract only, not a firmware or hardware qualification.',
                  'No scene recall, parameter write, Store, retry or automatic Undo.']))
