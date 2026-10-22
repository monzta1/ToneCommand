"""Additive firmware metadata composition, never a live write override.

Approved parent functionality stays in the child. Device-specific changes
are explicit patches, additions are separate, and deletions are rejected.
Registering and verifying a concrete firmware transport remains separate.
"""
from copy import deepcopy


def compose(parent, *, overrides=None, additions=None):
    if not isinstance(parent,dict) or any(not isinstance(v,dict) for v in parent.values()):
        raise ValueError('A complete approved parent catalog is required')
    result=deepcopy(parent)
    for family,controls in (overrides or {}).items():
        if family not in result or not isinstance(controls,dict):
            raise ValueError('Overrides may only patch existing parent families')
        for name,patch in controls.items():
            if name not in result[family] or not isinstance(patch,dict) or any(v is None for v in patch.values()):
                raise ValueError('Inherited parameters cannot be deleted or replaced by a missing definition')
            result[family][name].update(deepcopy(patch))
    for family,controls in (additions or {}).items():
        if not isinstance(controls,dict):raise ValueError('Additions must contain complete control definitions')
        for name,definition in controls.items():
            if name in result.get(family,{}) or not isinstance(definition,dict) or not definition:
                raise ValueError('New firmware controls cannot silently replace parent controls')
            result.setdefault(family,{})[name]=deepcopy(definition)
    # Duplicate wire addresses would make lookup depend on dictionary order.
    for family,controls in result.items():
        ids=[d.get('pid') for d in controls.values()]
        if any(type(pid) is not int for pid in ids) or len(set(ids))!=len(ids):
            raise ValueError('Firmware control addresses must be unique integers within each family')
    return result
