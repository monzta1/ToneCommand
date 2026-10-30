"""Device-bound full-plan reviews. No AI response can authorize sending."""
import secrets
import time
from copy import deepcopy

from . import executor, modifiers, route_guard, fw33_profile, nam_selector, nam_slots
from .controller_review import digest
from . import design_history
from .profile import validate_preset


def snapshot(dev, nam_slot=None, *, include_nam=True):
    with dev._lock:
        preset, scene, fw = dev.current_preset(), dev.current_scene(), dev.firmware_label()
        if not preset or type(scene) is not int or fw not in ('32.06',fw33_profile.KEY) or dev.reg.firmware != fw:
            raise ValueError('Current preset/scene or exact verified firmware is unavailable.')
        validate_preset(dev.reg, preset[0])
        blocks, grid = dev.status_dump(), dev.read_grid()
        if blocks is None or grid is None:
            raise ValueError('Block/grid read failed; nothing sent.')
        entries = modifiers.inspect(dev)
        if len(entries) != 32 or any(len(e['words']) != 25 for e in entries):
            raise ValueError('All 32 complete modifier records are required.')
        # 200/201 are captured system status records, not grid blocks with a
        # four-channel parameter dump. Keep them in the fingerprint, not bulk.
        bulk = {b.effect_id: dev.bulk_read(b.effect_id) for b in blocks
                if b.effect_id not in (200,201)}
        if any(not isinstance(words,list) or not words for words in bulk.values()):
            raise ValueError('A block could not be read completely.')
        names = [dev.scene_name(n) for n in range(1,9)]
        if any(not name for name in names):
            raise ValueError('Scene names could not be read.')
        if dev.current_preset() != preset or dev.current_scene() != scene:
            raise ValueError('Preset/scene changed during reading; refresh first.')
        capture = None
        captures = {}
        if fw == fw33_profile.KEY and (include_nam is True or (include_nam is None and 206 in bulk)):
            selected_slots = nam_selector.slots(bulk[206]) if 206 in bulk else [1]*4
            channel = next((b.channel for b in blocks if b.effect_id == 206), 0)
            if type(channel) is not int or channel not in range(4):
                raise ValueError('NAM channel cannot be read')
            slot = nam_slots.number(nam_slot) if nam_slot is not None else selected_slots[channel]
            for number in sorted(set(selected_slots + [slot])):
                got = nam_selector.capture(dev, number)
                captures[number] = dict(name=got.name,slot=got.slot,sha256=got.payload_sha256,
                                        bytes=got.byte_count)
            capture = captures[slot]
        if dev.current_preset() != preset or dev.current_scene() != scene:
            raise ValueError('Target changed during NAM reading; nothing sent')
        return dict(preset=preset, scene=scene, firmware=fw, blocks=blocks, grid=grid,
                    variant=getattr(dev.reg,'hardware_variant',None),
                    nam=capture, nam_captures=captures,
                    modifiers=entries, bulk=bulk, scene_names=names,
                    cabs=sorted((b,o,n) for (b,o),n in dev.reg.cab_catalog.names.items()))


def public_state(state, reg):
    try:
        ids = route_guard.serial_route(state['grid'], state['blocks'], reg)
        problem = None
    except ValueError as exc:
        ids, problem = None, str(exc)
    status = {b.effect_id:b for b in state['blocks']}
    route_blocks = [dict(label=route_guard.labels([eid],reg)[0],
        channel='ABCD'[status[eid].channel] if status[eid].channel in range(4) else '?',
        bypassed=status[eid].bypassed) for eid in ids or []]
    return dict(preset=state['preset'][0], name=state['preset'][1], scene=state['scene'],
        firmware=state['firmware'], route=route_guard.labels(ids,reg) if ids else [],
        route_blocks=route_blocks,
        nam=state.get('nam'),
        route_problem=problem, cab_count=len(state['cabs']),
        scene_names=state['scene_names'],
        warning='Scenes 5-8 can share edited channels. Their mappings are not inferred; '
                'review all affected sounds. No Store, automatic Undo or measured limiter.')


class Reviews:
    def __init__(self, clock=time.monotonic):
        self.clock, self.pending, self.last_sent = clock, None, None

    def refinement(self, dev, token, initial):
        prior=self.last_sent
        if (not prior or prior['device'] is not dev or not isinstance(token,str)
                or not token.isascii() or not secrets.compare_digest(prior['token'],token)):
            raise ValueError('Geen geverifieerd verzonden ontwerp in deze TC-sessie. Maak eerst een nieuw voorstel; TC raadt geen oude instellingen.')
        proof=prior['proof']
        if len(prior['plan']['scenes'])>1 and len(proof.get('scene_fingerprints',{}))!=len(prior['plan']['scenes']):
            raise ValueError('Voor deze meer-scene-route ontbreekt een volledige laatste scenecontrole. Geen veilige luisterbasis; niets verzonden.')
        expected=proof.get('scene_fingerprints',{}).get(str(initial['scene']),prior['stamp'])
        if digest(initial)!=expected:
            raise ValueError('De preset, kanaaltoewijzing of catalogus is gewijzigd sinds SEND. De luisterbasis is niet meer betrouwbaar; niets verzonden.')
        return deepcopy(prior['plan'])

    def resume(self,dev,record_id,*,expected_preset,external_audio_muted,target_confirmed):
        """New readback, new token; never execute saved actions or restore memory."""
        if external_audio_muted is not True or target_confirmed is not True:
            raise PermissionError('Confirm current target and external mute for all-scene checking')
        record=design_history.load(record_id)
        with dev._lock:
            if (record['preset']!=expected_preset or dev.reg.firmware!=record['firmware']
                    or getattr(dev.reg,'hardware_variant',None)!=record['variant']):
                raise ValueError('Saved design firmware, chassis or target differs; nothing resumed')
            initial=snapshot(dev,include_nam=False)
            if initial['preset'][0]!=expected_preset:
                raise ValueError('Select the saved target preset first; no automatic preset reload')
            proof=record['proof']
            if digest(initial)!=proof['scene_fingerprints'].get(str(initial['scene'])):
                raise ValueError('Device settings or imported cab names differ from saved design; nothing resumed')
            from . import album_planning,navigation,wah_voicing
            route=route_guard.serial_route(initial['grid'],initial['blocks'],dev.reg)
            count=record['plan']['design'].get('scene_count',8)
            controller=wah_voicing.existing_controller(initial['modifiers']) if record['plan']['design'].get('wah') else None
            plan=album_planning.compile_design(dev.reg,record['plan']['design'],route,count,
                controller['source'] if controller else None,controller['auto_engage'] if controller else None)
            if 'reference_measurements' in record['plan']:
                plan['reference_measurements']=deepcopy(record['plan']['reference_measurements'])
            if 'scene_contract' in record['plan']:
                from . import scene_contract
                plan['scene_comparison']=scene_contract.assess(plan,record['plan']['scene_contract'])
                plan['warnings'].extend(plan['scene_comparison']['warnings'])
            self.clear();self.last_sent=None
            # Scene selection is explicitly consented, but a mismatch never
            # triggers a rollback, old SEND, model write or preset reload.
            for number in range(1,count+1):
                if dev.current_scene()!=number:
                    navigation.switch_scene(dev,number,dev.current_preset(),external_audio_muted=True)
                now=snapshot(dev,include_nam=False)
                if digest(now)!=proof['scene_fingerprints'][str(number)]:
                    raise ValueError(f'Scene {number} changed; resume stopped, retain external mute')
            if digest(now)!=proof['final_fingerprint']:
                raise ValueError('Final saved scene proof differs; nothing resumed')
            navigation.switch_scene(dev,1,dev.current_preset(),external_audio_muted=True)
            now=snapshot(dev,include_nam=False)
            if digest(now)!=proof['scene_fingerprints']['1']:
                raise ValueError('Scene1 changed after the survey; resume stopped')
            token=secrets.token_urlsafe(32)
            self.last_sent=dict(token=token,device=dev,plan=deepcopy(plan),stamp=digest(now),proof=deepcopy(proof))
            return dict(ok=True,refine_token=token,preset=expected_preset,name=plan['name'],
                scenes=plan['scenes'],mode='amp',scene=1,stored=False,parameters_written=False,
                scenes_selected=True,history_id=record_id,
                warning=f'Alle {count} ontworpen scenes opnieuw gecontroleerd. Scene1 staat klaar voor bijsturen. Geen oude SEND/Store-toestemming hergebruikt; gedeelde IR-audio en hoorbare klank zijn niet gemeten.')

    def clear(self):
        self.pending = None

    def prepare(self, dev, plan, initial):
        self.clear()
        with dev._lock:
            now = snapshot(dev, initial['nam']['slot'] if initial.get('nam') else None,
                           include_nam=plan.get('mode') not in ('serial','album'))
            if digest(now) != digest(initial):
                raise ValueError('Preset changed while the AI was planning. Nothing sent; regenerate.')
            executor.prepare(dev,plan['actions'],plan['required_route'],now['preset'][0])
            token = secrets.token_urlsafe(32)
            self.pending = dict(token=token, device=dev, stamp=digest(now), plan=plan,
                                preset=now['preset'][0], expires=self.clock()+600)
            self.pending['nam_slot'] = now['nam']['slot'] if now.get('nam') else None
            self.pending['include_nam'] = plan.get('mode') not in ('serial','album')
            return dict(**plan, token=token, expires_in=600,
                        target=public_state(now,dev.reg), stored=False)

    def send(self, dev, token, *, target_confirmed, external_audio_muted):
        if target_confirmed is not True or external_audio_muted is not True:
            raise PermissionError('Confirm target and external audio mute first.')
        pending = self.pending
        if (not pending or not isinstance(token,str) or not token.isascii()
                or not secrets.compare_digest(pending['token'],token)):
            raise ValueError('Review missing, replaced or already used.')
        self.clear()
        if pending['device'] is not dev or self.clock() >= pending['expires']:
            raise ValueError('Review expired or connection changed; regenerate.')
        with dev._lock:
            if digest(snapshot(dev, pending['nam_slot'], include_nam=pending['include_nam'])) != pending['stamp']:
                raise ValueError('Device or cab catalogue changed since review. Nothing sent.')
            plan = pending['plan']
            self.last_sent=None
            dev._album_store_stamp=None
            dev._album_store_proof=None
            result = executor.execute(dev,plan['actions'],plan['required_route'],
                expected_preset=pending['preset'],external_audio_muted=True)
            if result['ok'] and plan.get('mode')=='album':
                proof=result.get('album_verification')
                fresh=digest(snapshot(dev,include_nam=False))
                if not proof or fresh!=proof['final_fingerprint']:
                    raise ValueError('Final state changed after verified album execution; no Store proof')
                dev._album_store_stamp=fresh
                dev._album_store_proof=proof
            if result['ok']:
                self.last_sent=dict(token=pending['token'],device=dev,plan=deepcopy(plan),
                    stamp=digest(snapshot(dev,pending['nam_slot'],include_nam=pending['include_nam'])),
                    proof=result.get('album_verification',{}))
                if len(plan['scenes'])==1 or len(result.get('album_verification',{}).get('scene_fingerprints',{}))==len(plan['scenes']):
                    result['refine_token']=pending['token']
                if plan.get('mode')=='album':
                    try:
                        result['history']=design_history.remember(plan,result['album_verification'],
                            snapshot(dev,include_nam=False))
                    except (OSError,ValueError,KeyError,TypeError) as exc:
                        # History failure cannot turn a successful hardware SEND
                        # into a retry or silently discard its same-session proof.
                        result['history_warning']='Preset verzonden, maar lokale ontwerpgeschiedenis niet bewaard: '+str(exc)
            # All action results are already independently verified by the executor.
            # No hidden scene switching for a final survey; that could itself alter
            # state. Report exactly what was executed and what remains unmeasured.
            return result
