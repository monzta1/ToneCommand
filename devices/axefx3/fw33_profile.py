"""Bounded FW33 beta controls measured with Axe-Edit, 2026-10-08 through17.

Only this exact identity/build is recognized. Metadata equality alone never
promotes model, routing, modifier, CAB/NAM install or permanent Store writes.
"""
from copy import deepcopy
from . import effect_controls_fw33 as effect_controls
from .firmware_inheritance import compose

KEY = '33.00-beta.20261006'
# Released after exact native calibration, normal AI/SEND and independent
# eight-scene editor acceptance; no end-user/environment override.
DRIVE_RELEASED = True
# Closed72-literal calibration, actual selected-AI333-action normal SEND and
# independent28-knob/four-scalar/Tempo NONE editor comparison passed on322.
AMP_ZERO_RELEASED = True
TEMPO_NONE_RELEASED = True
FX_ZERO_RELEASED = True
#16 captured editor frames, normal setters/full-state readback on329/325.
LEGACY_ZERO_RELEASED=True
LEGACY_ZERO_TYPED=frozenset({'WAH_INDUCTOR_BIAS','WAH_QTRACKING','WAH_FAT',
    'DISTORT_LEVEL','OUTPUT_LEVEL','REVERB_MIX'})
LEGACY_ZERO_NORMALIZED=frozenset({'WAH_RESONANCE','WAH_DRIVE'})
FX_ZERO_NAMES = frozenset({'DELAY_FEED','DELAY_MIX','CHORUS_DEPTH','CHORUS_MIX'})
# Released after native prefix1..8 normal SEND/full-state preservation and
# independent post-batch eight-scene editor comparison. Same fixed topology.
ALBUM_SCENE_COUNTS = frozenset(range(1,9))
IDENTITY = (0,1,116,16,8,97,0,16,1,17,0,0,79,99,116,32,32,54,32,
            50,48,50,54,32,49,54,58,50,50,58,53,51,0,0,0,0,0,0,0,0,0,0,0,0,21)
NAMES = {
    'DISTORT': ('DISTORT_DRIVE','DISTORT_BASS','DISTORT_MID','DISTORT_TREBLE',
                'DISTORT_MASTER','DISTORT_DEPTH','DISTORT_PRESENCE','DISTORT_LEVEL'),
    'WAH': ('WAH_FREQMIN','WAH_FREQMAX','WAH_RESONANCE','WAH_QTRACKING',
            'WAH_FAT','WAH_DRIVE','WAH_INDUCTOR_BIAS','WAH_LOWCUT','WAH_LEVEL','WAH_CONTROL'),
    'PEQ': tuple(f'PEQ_{field}{i}' for field in ('FREQ','GAIN') for i in range(1,6)) + ('PEQ_LEVEL',),
    'PITCH': ('PITCH_LEVEL',),
    'DELAY': ('DELAY_TIME','DELAY_FEED','DELAY_MIX','DELAY_LEVEL'),
    'REVERB': ('REVERB_TIME','REVERB_MIX','REVERB_LEVEL'),
    'OUTPUT': ('OUTPUT_LEVEL',),
    'CHORUS': ('CHORUS_RATE','CHORUS_DEPTH','CHORUS_MIX','CHORUS_LEVEL'),
    'COMP': tuple(effect_controls.DEFINITIONS['COMP']),
    'GEQ': tuple(effect_controls.DEFINITIONS['GEQ']),
    'FUZZ': ('FUZZ_DRIVE','FUZZ_TONE','FUZZ_LEVEL','FUZZ_MIX'),
    'NAM': ('NAM_INPUT_GAIN','NAM_BASS','NAM_MID','NAM_TREBLE','NAM_LEVEL'),
    'CABINET': tuple(f'CABINET_{field}{i}' for field in ('LEVEL','PAN','MUTE') for i in range(1,5)),
}
ZERO_TYPED = frozenset({'DELAY_LEVEL','REVERB_LEVEL','CHORUS_LEVEL','WAH_LEVEL','WAH_CONTROL',
                        'PITCH_LEVEL','PEQ_LEVEL',*(f'PEQ_GAIN{i}' for i in range(1,6)),
                        'NAM_INPUT_GAIN','NAM_LEVEL'}) | frozenset(NAMES['CABINET']) | frozenset(NAMES['FUZZ']) | effect_controls.ZERO_TYPED
LEVELS = frozenset({'DISTORT_LEVEL','WAH_LEVEL','DELAY_LEVEL','REVERB_LEVEL',
                   'CHORUS_LEVEL','OUTPUT_LEVEL','NAM_LEVEL'})
# Measured channel-A layouts; runtime also requires four channels and instance 1.
STRIDES = {'DISTORT':142,'WAH':25,'DELAY':89,'REVERB':71,'CHORUS':32,
           'COMP':37,'GEQ':20,'OUTPUT':26,'NAM':18,'CABINET':106,'FUZZ':44,'PEQ':33,'PITCH':116}
CONTROL_COUNT = sum(map(len, NAMES.values()))
# Complete empty-slot route independently constructed/read on muted preset 325.
# This is not a generic FW33 insertion/splice/parallel-route authorization.
NAM_ROUTE = (37,206,62,70,78,66,42)
BUILD_FAMILIES = frozenset({'NAM','CABINET','DELAY','CHORUS','REVERB'})
BUILD_KINDS = frozenset({'add_block','rename_preset','rename_scene',
                         'set_param','set_scene','set_channel','set_bypass','select_nam','store'})
# Existing exact NAM routes measured on preset 326; new foundations stay 1/A.
NAM_SCENES = frozenset({1,2})
NAM_CHANNELS = frozenset({0,1})


def identity_key(reply) -> str | None:
    return KEY if reply is not None and tuple(reply) == IDENTITY else None


def definitions(legacy: dict) -> dict:
    # The approved parent is the baseline, not a firmware-specific whitelist
    # rebuilt from scratch. Encoding deltas remain explicit and tested.
    result = compose(legacy)
    for name in NAMES['DISTORT'][:-1]:
        result['DISTORT'][name].update(set_divisor=10.0,display_tolerance=.011)
    # FW33 observed editor SET domains, distinct from normalized bulk laws.
    result['WAH']['WAH_LEVEL'].update(set_opcode='09',set_divisor=1.0,
                                    display_tolerance=.051)
    result['WAH']['WAH_CONTROL'].update(set_opcode='09',set_divisor=10.0,
                                      display_tolerance=.011)
    result.setdefault('CHORUS',{}).update({
        'CHORUS_RATE':dict(pid=2,label='Rate',unit='Hz',min=.1,max=10.,scale='log10',
                           set_divisor=1.,set_opcode='09',display_tolerance=.0011,tempo_param_id=3),
        'CHORUS_DEPTH':dict(pid=4,label='Depth',unit='%',min=0.,max=100.,
                            set_divisor=100.,set_opcode='09',display_tolerance=.051),
        'CHORUS_MIX':dict(pid=10,label='Mix',unit='%',min=0.,max=100.,
                          set_divisor=100.,set_opcode='09',display_tolerance=.051),
        'CHORUS_LEVEL':dict(pid=11,label='Level',unit='dB',min=-80.,max=20.,
                            set_divisor=1.,set_opcode='09',display_tolerance=.051),
    })
    for family,controls in effect_controls.DEFINITIONS.items():
        result.setdefault(family,{}).update(deepcopy(controls))
    from .tone_controls import DEFINITIONS
    result.setdefault('FUZZ',{}).update(deepcopy(DEFINITIONS['FUZZ']))
    # NAM Player 1, effect 206: captured editor SETs, independently verified
    # display queries and exact 72-word restoration. This does NOT authorize
    # capture/model selection, block insertion or persistent NAM installation.
    result.setdefault('NAM',{}).update({
        'NAM_INPUT_GAIN':dict(pid=5,label='Input Gain',unit='dB',min=-20.,max=20.,
                              set_divisor=1.,set_opcode='09',display_tolerance=.011),
        'NAM_LEVEL':dict(pid=1,label='Level',unit='dB',min=-80.,max=20.,
                         set_divisor=1.,set_opcode='09',display_tolerance=.051),
        **{name:dict(pid=pid,label=label,unit='',min=0.,max=10.,
                     set_divisor=10.,set_opcode='09',display_tolerance=.011)
           for name,pid,label in (('NAM_BASS',10,'Bass'),('NAM_MID',11,'Mid'),
                                  ('NAM_TREBLE',12,'Treble'))},
    })
    for controls in result.values():
        for data in controls.values():
            data.update(firmware_versions=(KEY,),hardware_verified=True,
                        bulk_restore_supported=True)
    for family in effect_controls.MODELS:
        for data in result[family].values():data['bulk_restore_supported']=False
    # Display SET/display+bulk readback is not approval of raw undo writes.
    for family in ('PEQ','PITCH'):
        for data in result[family].values():data['bulk_restore_supported']=False
    return result
