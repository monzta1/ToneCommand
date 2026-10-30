"""Explicit synthetic scene intentions for mocked AI protocol tests."""
from copy import deepcopy


def with_goals(raw):
    raw=deepcopy(raw)
    if 'albums' in raw:
        from devices.axefx3.album_planning import layout
        raw['scene_layout']=layout(raw)
        names=[s['name'] for s in raw['scene_layout']]
    else:
        names=[s['name'] for s in raw['scenes']] if 'scenes' in raw else [raw['scene_name']]
    raw['scene_goals']=[dict(scene=n,target='Synthetic requested tone',role=name,
        realization='Synthetic settings follow this requested role.',distinct_from=[],distinction='shared')
        for n,name in enumerate(names,1)]
    return raw
