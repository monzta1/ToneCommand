"""User-declared chassis and conservative cab/NAM memory policy, not write evidence."""
from . import fw33_profile


def memory_policy(firmware, variant=None):
    # Only the old verified profile is known to retain both user IR banks.
    # Unknown/beta firmware is treated as NAM-era for storage protection.
    old = firmware == '32.06'
    user2 = old or variant == 'mk2'
    return dict(variant=variant, variant_verified=False,
                user2_cabs=user2, nam_storage='user2' if variant == 'mk1' and not old else
                'separate' if variant == 'mk2' and not old else 'unverified',
                nam_writes=firmware == fw33_profile.KEY and variant == 'mk2',
                write_supported=old or firmware == fw33_profile.KEY,
                warning='The chassis is declared by the user, not proven by the device. '
                + ('NAM: measured FW33/MK2/Windows profile; installation in slots 001-256 after slot selection. Preset builds explicitly choose a fully read installed slot; selection and installation are separate. '
                 if firmware == fw33_profile.KEY else 'NAM placement/installation is not verified. ')
                + ('User2 is available for cab names.' if user2 else
                   'Do not use User2 as a cab bank: on MK1 with NAM firmware it is NAM memory.'))


def apply(reg, variant):
    if variant not in (None, 'mk1', 'mk2'):
        raise ValueError('Choose Axe-Fx III MK1 or MK2.')
    reg.hardware_variant = variant
    policy = memory_policy(reg.firmware, variant)
    reg.cab_catalog.restrict_user2(policy['user2_cabs'])
    from . import cab_metadata
    try:
        policy['cab_names_restored']=cab_metadata.restore_if_empty(reg)
    except (OSError,ValueError,TypeError,KeyError):
        policy['cab_names_restored']=0
        reg.cab_catalog.cache_note='Local cab names could not be read; import the current name list again.'
    reg.cab_rosters = reg.cab_catalog.rosters()
    return policy
