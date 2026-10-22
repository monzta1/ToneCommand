"""Separate, expiring confirmation for a measured same-slot FW33 Store."""
import secrets
import time

from fm9.device import get_store_slots
from . import fw33_profile, tone_review, route_guard,serial_build,navigation
from .controller_review import digest


class Stores:
    def __init__(self):
        self.pending=None

    def prepare(self,dev,expected_preset):
        self.pending=None
        if getattr(dev.reg,'hardware_variant',None) != 'mk2':
            raise ValueError('FW33 Store requires the declared measured MK2 profile')
        if type(expected_preset) is not int or expected_preset not in get_store_slots():
            raise ValueError('Store target must be in the existing preset allowlist')
        state=tone_review.snapshot(dev,include_nam=None)
        if state['firmware'] != fw33_profile.KEY or state['preset'][0] != expected_preset:
            raise ValueError('Store requires the exact FW33 current target')
        route=tuple(route_guard.serial_route(state['grid'],state['blocks'],dev.reg))
        if route==serial_build.ROUTE:
            proof=getattr(dev,'_album_store_proof',None)
            count=len(proof.get('scene_fingerprints',{})) if isinstance(proof,dict) else 0
            if (getattr(dev,'_album_store_stamp',None)!=digest(state) or not proof
                    or proof.get('final_fingerprint')!=digest(state)
                    or count not in fw33_profile.ALBUM_SCENE_COUNTS
                    or set(proof.get('scene_fingerprints',{}))!={str(n) for n in range(1,count+1)}):
                raise ValueError('AMP/CAB Store requires an unchanged complete successful SEND for every designed scene on this connection')
        elif route!=fw33_profile.NAM_ROUTE:
            raise ValueError('Store requires the complete measured NAM route or completed album SEND')
        before=dev.slot_name(expected_preset)
        if before is None or before.number != expected_preset:
            raise ValueError('Stored destination cannot be read')
        token=secrets.token_urlsafe(32)
        self.pending=dict(token=token,device=dev,stamp=digest(state),before=before,
                          preset=expected_preset,album=route==serial_build.ROUTE,count=count if route==serial_build.ROUTE else 0,
                          proof=getattr(dev,'_album_store_proof',None) if route==serial_build.ROUTE else None,
                          expires=time.monotonic()+600)
        return dict(token=token,preset=expected_preset,name=state['preset'][1],
                    replaces=before.name,permanent=True,readonly=True,expires_in=600,
                    verification_note=(f'Voor Store selecteert TC onder externe mute alle {"acht" if count==8 else count} scenes voor controle, zonder hun instellingen te herschrijven. Eindigt op scene{count}.' if route==serial_build.ROUTE else ''))

    def send(self,dev,token,external_audio_muted,confirm_permanent_write):
        if external_audio_muted is not True or confirm_permanent_write is not True:
            raise PermissionError('Confirm external mute and permanent preset storage separately')
        pending=self.pending
        self.pending=None
        if (not pending or pending['device'] is not dev or not isinstance(token,str)
                or not token.isascii() or not secrets.compare_digest(token,pending['token'])
                or time.monotonic() >= pending['expires']):
            raise ValueError('Store review expired, replaced or already used')
        with dev._lock:
            if pending['album'] and getattr(dev,'_album_store_stamp',None)!=pending['stamp']:
                raise ValueError('Successful album SEND proof was invalidated; nothing stored')
            if digest(tone_review.snapshot(dev,include_nam=None)) != pending['stamp'] or dev.slot_name(pending['preset']) != pending['before']:
                raise ValueError('Preset, NAM memory or stored target changed; nothing stored')
            if pending['album']:
                for number in range(1,pending['count']+1):
                    navigation.switch_scene(dev,number,dev.current_preset(),external_audio_muted=True)
                    if digest(tone_review.snapshot(dev,include_nam=False))!=pending['proof']['scene_fingerprints'][str(number)]:
                        dev._album_store_stamp=None;dev._album_store_proof=None
                        raise ValueError('Saved scene mapping or full state changed; nothing stored')
                if digest(tone_review.snapshot(dev,include_nam=False))!=pending['stamp']:
                    raise ValueError('Final Store verification changed; nothing stored')
            with dev.edit_session(external_audio_muted=True,expected_preset=pending['preset']):
                slot,name=dev.store_preset(pending['preset'])
            return dict(ok=True,stored=True,preset=slot,name=name,reloaded=False,audio_verified=False)
