"""Allocate eight scenes to four channels without overwriting shared voicing.

Pure planning logic, not firmware evidence or permission to transmit.
Bypass is scene state. Only identical stored settings can share a channel.
"""
import json


def allocate(configurations, family, *, independent=False):
    if not 1 <= len(configurations) <= 8:
        raise ValueError('Plan requires one to eight scenes')
    if independent and len(configurations) <= 4:
        return list(range(len(configurations)))
    keys = []
    assigned = []
    for config in configurations:
        if config is None:
            assigned.append(0)
            continue
        key = json.dumps(config, sort_keys=True, allow_nan=False, separators=(',', ':'))
        if key not in keys:
            if len(keys) == 4:
                raise ValueError(f'{family}: more than four different channel settings. '
                                 'Reuse identical voicing and scene bypass, or simplify the design; nothing sent.')
            keys.append(key)
        assigned.append(keys.index(key))
    return assigned


def settings(config):
    if config is None:
        return None
    return config.model_dump(exclude={'active'})
