"""Read-only controller proposals with single-use, state-bound send tickets."""
from dataclasses import asdict, is_dataclass
import hashlib
import json
import secrets
import time

from . import modifiers, pedal_control as pedal, pitch_control

LABELS = {94: "Wah 1 / Control", 95: "Wah 2 / Control", 102: "Volume 1 / Volume",
          110: "Pitch 1 / Octave pedal"}


def digest(value):
    def encode(item):
        if is_dataclass(item):
            return asdict(item)
        raise TypeError("Unexpected device snapshot value")
    return hashlib.sha256(json.dumps(value, default=encode, sort_keys=True).encode()).hexdigest()


def inspect(dev):
    """No connection, selection, modifier allocation or SET is performed."""
    with dev._lock:
        preset, scene = dev.current_preset(), dev.current_scene()
        blocks = dev.status_dump()
        if preset is None or scene is None or blocks is None:
            raise ValueError("Preset or block state could not be read. Nothing sent.")
        slots = modifiers.inspect(dev)
        targets = []
        for block in blocks:
            eid = block.effect_id
            if eid not in LABELS:
                continue
            if eid==110:
                reason=None;entry=None
                try:
                    writer=pitch_control.Writer(dev)
                    state=writer.observe()
                    index=pitch_control.owner(state)
                    entry=state['modifiers'][index] if index is not None else None
                except (ValueError,RuntimeError,OSError) as exc:
                    reason=str(exc)
                targets.append(dict(effect_id=eid,label=LABELS[eid],
                    source=entry[0] if entry else None,
                    source_name=modifiers.SOURCE_NAMES.get(entry[0],'NONE') if entry else 'NONE',
                    auto_engage='Off' if entry else None,writable=reason is None,reason=reason,
                    modes=['Off'],operation='pitch_setup',
                    notice='Existing Pitch 1/A only: Advanced Whammy, heel 0 to toe +12 semitones, 100% wet. The chosen External source is restricted to channel A, with Auto Engage Off. SEND activates Pitch in the current scene. No placement, global CC mapping or Store.'))
                continue
            found = [s for s in slots if (s['effect_id'], s['param_id']) == (eid, pedal.TARGETS[eid])]
            entry = found[0] if len(found) == 1 else None
            reason = None
            try:
                pedal.preflight(dev, eid, 12)
            except (ValueError, RuntimeError, OSError) as exc:
                reason = str(exc)
            targets.append(dict(effect_id=eid, label=LABELS[eid],
                source=entry['source'] if entry else None,
                source_name=entry['source_name'] if entry else 'Geen controller',
                auto_engage=(entry.get('observed_target') or {}).get('auto_engage_name') if entry else None,
                writable=reason is None, reason=reason,
                modes=['Off'] if eid == 102 else ['Off', 'Fast Pos']))
        if dev.current_preset() != preset or dev.current_scene() != scene:
            raise ValueError("Preset/scene changed during reading; refresh first.")
        return dict(preset=preset[0], preset_name=preset[1], scene=scene,
                    firmware=dev.reg.firmware, targets=targets,
                    sources=[dict(value=12, label='External 1'), dict(value=13, label='External 2')])


class Reviews:
    """One pending proposal. The host serializes calls with its device lock."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.pending = None

    def clear(self):
        if self.pending and self.pending.get('pitch_writer'):
            self.pending['pitch_writer'].pending=None
        self.pending = None

    def prepare(self, dev, request):
        self.clear()
        request = dict(request)
        with dev._lock:
            if request.get('effect_id')==110:
                if set(request)-{'effect_id','source','auto_engage'} or request.get('auto_engage') not in (None,'Off'):
                    raise ValueError('Pitch octave setup supports Auto Engage Off only')
                writer=pitch_control.Writer(dev,clock=self.clock)
                proposal,before=writer.prepare(pitch_control.Setup(request.get('source')))
                index=pitch_control.owner(before)
                entry=before['modifiers'][index] if index is not None else None
                token=secrets.token_urlsafe(32)
                self.pending=dict(token=token,device=dev,pitch_writer=writer,pitch_review=proposal,
                    expires=proposal.expires,preset=before['preset'][0])
                return dict(token=token,expires_in=60,preset=before['preset'][0],preset_name=before['preset'][1],
                    scene=before['scene'],target=LABELS[110],stored=False,
                    before_source=modifiers.SOURCE_NAMES.get(entry[0],'NONE') if entry else 'NONE',
                    after_source=modifiers.SOURCE_NAMES[request['source']],before_auto='Off' if entry else None,
                    after_auto='Off',new_binding=index is None,operation='pitch_setup',
                    setup='Advanced Whammy on Pitch 1/A; heel 0 to toe +12 semitones; mix 100%; level 0dB after quiet staging; full-range linear controller on A only. Activate in the current scene; other scenes using A share this voice. Existing custom/other Pitch modifiers refuse. No global CC changes, insertion or permanent storage.')
            slots, context, slot = pedal.preflight(dev, **request)
            before = slots[slot - 1] if slot else None
            token = secrets.token_urlsafe(32)
            self.pending = dict(token=token, device=dev, request=request,
                                stamp=digest([slots, context]), expires=self.clock() + 300,
                                preset=context[0][0])
            return dict(token=token, expires_in=300, preset=context[0][0],
                preset_name=context[0][1], scene=context[1], target=LABELS[request['effect_id']],
                before_source=before['source_name'] if before else 'Geen controller',
                after_source=modifiers.SOURCE_NAMES[request['source']],
                before_auto=(before.get('observed_target') or {}).get('auto_engage_name') if before else None,
                after_auto=request.get('auto_engage') or 'Behouden (nieuw: Off)',
                new_binding=slot is None, stored=False)

    def send(self, dev, token, *, external_audio_muted, target_confirmed):
        if external_audio_muted is not True or target_confirmed is not True:
            raise PermissionError("Confirm target and external audio mute before sending.")
        pending = self.pending
        if (not pending or not isinstance(token, str) or not token.isascii()
                or not secrets.compare_digest(pending['token'], token)):
            raise ValueError("Review missing, replaced or already used. Review again.")
        # Consume before any further I/O. A failed/uncertain write must not be retried.
        self.pending=None
        if pending['device'] is not dev or self.clock() >= pending['expires']:
            raise ValueError("Review expired or connection changed. Review again.")
        with dev._lock:
            if pending.get('pitch_writer'):
                result=pending['pitch_writer'].apply(pending['pitch_review'],
                    external_audio_muted=True,target_confirmed=True)
                result['operation']='pitch_setup'
                return result
            slots, context, _ = pedal.preflight(dev, **pending['request'])
            if digest([slots, context]) != pending['stamp']:
                raise ValueError("Device state changed after review. Nothing sent; review again.")
            result = pedal.execute(dev, [pending['request']], expected_preset=pending['preset'],
                                   external_audio_muted=True)
            result['results'] = [asdict(r) for r in result['results']]
            return result
