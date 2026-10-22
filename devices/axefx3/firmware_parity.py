"""Read-only migration inventory. A registry entry is not write permission.

Every FW32.06 parameter must survive in FW33 or have an explicit migration
record. Encoders, block instances, controller operations and planner routes
are separate contracts; copying metadata never releases a device operation.
"""
from . import fw33_profile
from .evidence import AXE_FX_III_PARAM_DEFINITIONS as LEGACY

PENDING = {}
ENCODER_MIGRATIONS = frozenset({
    'DISTORT_DRIVE','DISTORT_BASS','DISTORT_MID','DISTORT_TREBLE',
    'DISTORT_MASTER','DISTORT_DEPTH','DISTORT_PRESENCE','WAH_LEVEL','WAH_CONTROL',
})
INSTANCE_MIGRATIONS = frozenset({
    ('DISTORT',2),
    *((family,i) for family in ('CABINET','DELAY','OUTPUT','REVERB','WAH','PITCH') for i in (2,3,4)),
})
ENCODING_FIELDS = ('pid','min','max','scale','set_opcode','set_divisor','wire_min','kind','enum_count')


def operation_migrations(reg):
    """Do not confuse complete parameter names with complete musical workflows."""
    if reg.firmware=='32.06':return []
    from . import pedal_fw33,wah_voicing
    mk2=getattr(reg,'hardware_variant',None)=='mk2'
    return [dict(function=name,status='retained' if ready else 'pending',scope=scope) for name,ready,scope in (
        ('wah_controller',pedal_fw33.RELEASED and mk2,'Wah1/2, External1/2, Off/Fast Pos, unchanged global CC mapping'),
        ('wah_tone_planner',wah_voicing.RELEASED and mk2,'Cry Babe on shared A, explicit scene bypass and controller in AMP/CAB builds'),
        ('volume_controller',pedal_fw33.VOLUME_RELEASED and mk2,'Volume/Pan1, External1/2, full-range native curve, Auto Engage Off'),
        ('remaining_effect_models',False,'Other approved FW32 effect models need their FW33 selector mapping; no ordinal fallback'),
        ('additional_numeric_instances',False,'First-instance acceptance does not enable other physical block instances'),
        ('additional_effect_channels',False,'Non-album effect channel changes require separate acceptance; no inferred A-D support'),
        ('flexible_serial_insertion',False,'Normal FW33 builds still use measured NAM or14-block AMP/CAB topology'),
        ('peq_pitch_tone_planner',False,'PEQ1 and Pitch1 Level setters are available on measured A; not new pitch shifting or planner topology'),
        ('amp_cab_reverb_delay_variants',False,'The FW33 AMP/CAB planner does not yet reproduce the older flexible Reverb and multiple Delay voices'),
        ('remaining_legacy_zero_setters',fw33_profile.LEGACY_ZERO_RELEASED and mk2,'Captured scalar zero variants; no alternate-opcode or epsilon fallback'),
        ('exact_raw_restore',False,'No FW33 raw-word restore or automatic Undo is enabled by metadata inheritance'),
    )]


def parameters(current):
    """Compare actual loaded definitions, without opening MIDI or changing them."""
    rows = []
    for family, definitions in LEGACY.items():
        for name, old in definitions.items():
            new = current.get(family,{}).get(name)
            changed = [field for field in ENCODING_FIELDS if new is not None and
                old.get(field, 'float' if field=='kind' else None) != new.get(field, 'float' if field=='kind' else None)]
            rows.append(dict(family=family,parameter=name,
                status='pending' if new is None else 'migrated_encoding' if changed else 'retained_definition',
                changed_fields=changed,
                reason=PENDING.get(name,'Unaccounted firmware regression') if new is None else None))
    return rows


def report(reg):
    if reg.firmware not in ('32.06',fw33_profile.KEY):
        return dict(baseline='32.06',firmware=reg.firmware,recognized=False,
                    automatically_enables_writes=False)
    rows = parameters(reg.definitions)
    old_names = {name for controls in LEGACY.values() for name in controls}
    added = sorted(name for controls in reg.definitions.values() for name in controls if name not in old_names)
    pending = [r for r in rows if r['status']=='pending']
    retained = [r for r in rows if r['status']!='pending']
    operations=operation_migrations(reg)
    from . import pedal_fw33,wah_voicing
    return dict(baseline='32.06',firmware=reg.firmware,recognized=True,
        baseline_parameters=len(rows),retained_parameters=len(retained),
        added_parameters=added,pending_parameters=pending,
        operation_migrations=operations,
        functionality_complete=not pending and not any(r['status']=='pending' for r in operations),
        migrated_encodings=[r for r in rows if r['status']=='migrated_encoding'],
        wah_controller_workspace=(reg.firmware=='32.06' or
            (pedal_fw33.RELEASED and getattr(reg,'hardware_variant',None)=='mk2')),
        wah_in_fw33_tone_planner=(reg.firmware==fw33_profile.KEY and wah_voicing.RELEASED
            and getattr(reg,'hardware_variant',None)=='mk2'),
        note='Definitions are not model/channel/instance/route permissions. Independent hardware acceptance remains required.',
        automatically_enables_writes=False)
