"""User-declared chassis and conservative cab/NAM memory policy, not write evidence."""
from . import fw33_profile
from .chassis import declared


def preset_count(reg):
    """Documented capacity, not hardware write approval or a Store allowlist."""
    return declared(getattr(reg, 'hardware_variant', None), allow_unknown=True).presets


def validate_preset(reg, number):
    if type(number) is not int or number not in range(preset_count(reg)):
        raise ValueError(f'Preset must be 0..{preset_count(reg)-1} for this chassis profile.')
    return number


def memory_policy(firmware, variant=None):
    # Only the old verified profile is known to retain both user IR banks.
    # Unknown/beta firmware is treated as NAM-era for storage protection.
    old = firmware == '32.06'
    chassis = declared(variant, allow_unknown=True)
    user2 = old or chassis.retains_user2_with_nam
    return dict(variant=variant, variant_verified=False,
                control_family=chassis.control_family,
                preset_count=chassis.presets,
                persistent_fullres_slots=chassis.persistent_fullres,
                user2_cabs=user2, nam_storage='user2' if variant == 'mk1' and not old else
                'separate' if variant == 'mk2' and not old else 'unverified',
                nam_writes=firmware == fw33_profile.KEY and variant == 'mk2',
                write_supported=old or firmware == fw33_profile.KEY,
                warning='The chassis is declared by the user, not proven by the device. '
                + ('NAM: measured FW33/MK2/Windows profile; installation in slots 001-256 after slot selection. Preset builds explicitly choose a fully read installed slot; selection and installation are separate. '
                 if firmware == fw33_profile.KEY and variant == 'mk2' else 'NAM placement/installation is not verified for this firmware/chassis. ')
                + ('User2 is available for cab names.' if user2 else
                   'Do not use User2 as a cab bank: on MK1 with NAM firmware it is NAM memory.'))


def apply(reg, variant):
    if variant not in (None, 'mk1', 'mk2'):
        raise ValueError('Choose Axe-Fx III MK1 or MK2.')
    reg.hardware_variant = variant
    policy = memory_policy(reg.firmware, variant)
    reg.cab_catalog.restrict_user2(policy['user2_cabs'])
    reg.cab_catalog.restrict_fullres(policy['persistent_fullres_slots'] > 0)
    from . import cab_metadata
    try:
        policy['cab_names_restored']=cab_metadata.restore_if_empty(reg)
    except (OSError,ValueError,TypeError,KeyError):
        policy['cab_names_restored']=0
        reg.cab_catalog.cache_note='Local cab names could not be read; import the current name list again.'
    reg.cab_rosters = reg.cab_catalog.rosters()
    return policy
