"""Musical block vocabulary and route-specific planning facts, never SET rights.

The block vocabulary follows the III columns in the official Blocks Guide
(June 2023). It is a baseline, not a claim to discover every future firmware
addition. Firmware/chassis acceptance and the selected builder remain distinct
from a block existing in the device or having a metadata/model name.
"""
from typing import Literal


# key: (display name, musical purpose). No MIDI addresses or raw parameters.
EFFECTS = {
    'drive': ('Drive', 'Shape preamp attack, saturation, boost or fuzz.'),
    'compressor': ('Compressor', 'Control dynamics and sustain without masking attack.'),
    'graphic_eq': ('Graphic EQ', 'Shape broad frequency regions.'),
    'parametric_eq': ('Parametric EQ', 'Shape selected frequency bands precisely.'),
    'post_eq': ('Post EQ', 'Shape the amplified tone with a graphic or parametric EQ.'),
    'delay': ('Delay', 'Add discrete echoes appropriate to the passage.'),
    'reverb': ('Reverb', 'Add room, plate, hall or other acoustic decay.'),
    'chorus': ('Chorus', 'Add modulation, doubling or width, not an output boost.'),
    'flanger': ('Flanger', 'Add a moving comb-filter character.'),
    'phaser': ('Phaser', 'Add a sweeping phase-filter character.'),
    'rotary': ('Rotary', 'Add rotating-speaker modulation.'),
    'tremolo': ('Tremolo/Panner', 'Modulate level or stereo position.'),
    'wah': ('Wah', 'Move a resonant filter; this is not pitch transposition.'),
    'wah_controller': ('Wah controller', 'Bind a user-selected source to a wah sweep.'),
    'pitch': ('Pitch', 'Transpose, detune or harmonize, including pedal pitch.'),
    'volume': ('Volume/Pan', 'Control signal level or stereo balance.'),
    'volume_controller': ('Volume controller', 'Bind a user-selected source to volume.'),
    'enhancer': ('Enhancer', 'Add spatial width with mono compatibility in mind.'),
    'filter': ('Filter', 'Apply low-pass, high-pass or other filtering.'),
    'formant': ('Formant', 'Add vowel-like filtering.'),
    'gate': ('Gate/Expander', 'Reduce unwanted signal between notes without cutting sustain.'),
    'dynamic_distortion': ('Dynamic Distortion', 'Add level-dependent distortion shaping.'),
    'multiband_compressor': ('Multiband Compressor', 'Control dynamics separately across frequency bands.'),
    'multitap_delay': ('Multitap Delay', 'Create multiple independently arranged echoes.'),
    'plex_delay': ('Plex Delay', 'Create interacting delay and pitch textures.'),
    'megatap_delay': ('Megatap Delay', 'Create dense multi-echo patterns.'),
    'ten_tap_delay': ('Ten-Tap Delay', 'Arrange up to ten echoes in time and space.'),
    'resonator': ('Resonator', 'Add tuned resonances or chord-like textures.'),
    'ring_modulator': ('Ring Modulator', 'Add metallic sum/difference-frequency textures.'),
    'synth': ('Synth', 'Generate pitch-tracking synthesized voices.'),
    'vocoder': ('Vocoder', 'Shape a carrier using a separate modulating signal.'),
    'looper': ('Looper', 'Record and replay a performance loop.'),
    'ir_player': ('IR Player', 'Process an impulse response outside the cabinet block.'),
    'tone_match': ('Tone Match', 'Apply a measured matching filter, not infer one from a title.'),
    'crossover': ('Crossover', 'Split the signal into frequency-dependent paths.'),
    'mixer': ('Mixer', 'Combine paths with explicit gain staging.'),
    'multiplexer': ('Multiplexer', 'Select among signal paths.'),
    'send_return': ('Feedback Send/Return', 'Create explicit internal routing; feedback needs separate validation.'),
    'scene_midi': ('Scene MIDI', 'Send scene-dependent MIDI; this can affect external equipment.'),
    'rta': ('Realtime Analyzer', 'Inspect frequency content; it is not a tone-generating effect.'),
}
Feature = Literal[tuple(EFFECTS)]

RULES = '''Choose effects for a musical purpose, not to fill the grid. Consider
the full vocabulary, but executable=true applies only to this selected route,
firmware and chassis. Block existence, a catalog name, a bypassable reserve
block or a level setter is NOT complete model/voicing/insertion support.
State each necessary effect in the scene's required_features, including effects
you choose to realize its target. Do not silently replace or omit a required
effect because execution is unavailable. Explain the exact limitation and ask
whether the user wants an available alternative; do not ask routine tuning
questions for supported effects. A wah filter is not pedal pitch. A stored
IR is not a Tone Match measurement. Use only the documented channels and route;
eight scenes do not create eight parameter channels. Keep user-selected
controller sources, routing, gain staging and review/SEND consent separate.
Never construct feedback loops or emit Scene MIDI from a conceptual suggestion.
'''


def _profiles(reg, mode):
    """Read existing acceptance gates; never promote a model or firmware here."""
    from . import serial_build, fw33_profile, effect_voicing, wah_voicing, models
    if mode not in ('amp', 'serial', 'nam'):
        raise ValueError('Choose an explicit AMP, serial or NAM planning route')
    result = {}
    measured = serial_build.supported(reg)
    if measured and mode in ('amp', 'serial', 'nam'):
        result.update(delay=('Retained model', 'Shared A'),
                      chorus=('Retained model', 'Shared A'))
    if measured and mode == 'amp':
        if fw33_profile.DRIVE_RELEASED:
            result['drive'] = ('T808 Mod', 'A-D follow the Amp channel')
        if effect_voicing.COMPRESSOR_RELEASED:
            result['compressor'] = ('Modern VCA Compressor', 'A-D follow the Amp channel')
        if effect_voicing.GEQ_RELEASED:
            result['graphic_eq'] = ('10 Band Variable Q, cut-only', 'A-D follow the Amp channel')
            result['post_eq'] = result['graphic_eq']
        if wah_voicing.reference(reg)['executable']:
            result['wah'] = ('Cry Babe', 'Shared A')
            result['wah_controller'] = ('External 1/2; Off/Fast Pos', 'Shared A; server-owned binding')
    if measured and mode == 'nam':
        result['reverb'] = ('Retained model', 'Shared A; NAM foundation has 1 scene, existing route up to 2')
    # Historical text compiler support is not inherited by MK1 or newer builds.
    if reg.firmware == '32.06' and mode == 'amp':
        for feature, family in (('delay', 'DELAY'), ('chorus', 'CHORUS'),
                                ('reverb', 'REVERB'), ('drive', 'FUZZ'), ('compressor', 'COMP')):
            names = list(models.roster(reg, family, selectable=True).values())
            if names:
                result[feature] = (', '.join(names), 'At most four independently allocated channels')
        result['wah'] = ('Preserved existing Wah voice', 'Explicit per-scene bypass; no new voicing')
        result['wah_controller'] = ('External 1/2; Off/Fast Pos', 'Server-owned binding, not global CC mapping')
        result['graphic_eq'] = ('Existing 10 Band Variable Q, cut-only', 'Existing first EQ block required')
        result['parametric_eq'] = ('Existing five-band voicing, cut-only', 'Existing first EQ block; preserve Q/filter types')
        result['post_eq'] = ('Existing Graphic EQ or Parametric EQ, cut-only', 'Existing first EQ block required')
    return result


def reference(reg, mode='amp'):
    from . import fw33_profile
    profiles = _profiles(reg, mode)
    unknown = reg.firmware not in ('32.06', fw33_profile.KEY)
    effects = []
    for key, (label, purpose) in EFFECTS.items():
        profile = profiles.get(key)
        effects.append(dict(key=key, label=label, purpose=purpose,
            executable=profile is not None,
            scope=dict(models=profile[0], channels=profile[1]) if profile else None,
            limitation=None if profile else (
                'Current firmware is not accepted by this normal preset builder.' if unknown else
                'This route has no complete verified insertion, voicing and scene compiler for this effect.')))
    return dict(route=mode, firmware=reg.firmware,
        chassis=getattr(reg, 'hardware_variant', None), effects=effects,
        vocabulary_source='Official III Blocks Guide, June 2023; baseline, not live inventory',
        requires_current_route_and_state_validation=True,
        hardware_write_authorized=False, all_effects_executable=len(profiles)==len(EFFECTS))


def executable(reg, mode):
    return sorted(_profiles(reg, mode))


def realized(feature, sound, controller):
    """Check compiled scene facts, not prose, names or a level-only stub.

    Features with no complete current scene representation always fail here.
    Adding one requires its canonical scene representation and regression tests,
    not just adding a name to the musical vocabulary.
    """
    effects = sound['effects']
    def active(key):
        value = effects.get(key)
        return bool(value) and (not isinstance(value, dict) or bool(value.get('active'))
            and value.get('mix', 1) > 0)
    if feature in ('delay', 'reverb', 'drive', 'compressor', 'wah'):
        return active(feature)
    if feature == 'chorus':
        return active('chorus') and effects['chorus'].get('depth', 1) > 0
    if feature == 'wah_controller':
        return bool(controller and controller.get('source')) and active('wah')
    def shaping(key):
        voice = effects.get(key)
        return active(key) and isinstance(voice, dict) and (
            any(voice.get('gains', [])) or any(b.get('gain') for b in voice.get('bands', [])))
    if feature == 'graphic_eq':
        return shaping('geq')
    if feature == 'parametric_eq':
        return shaping('peq')
    if feature == 'post_eq':
        return shaping('geq') or shaping('peq')
    return False
