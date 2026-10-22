"""Read-only controller proposals with single-use, state-bound send tickets."""
from dataclasses import asdict, is_dataclass
import hashlib
import json
import secrets
import time

from . import modifiers, pedal_control as pedal

LABELS = {94: "Wah 1 / Control", 95: "Wah 2 / Control", 102: "Volume 1 / Volume"}


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
        self.pending = None

    def prepare(self, dev, request):
        self.clear()
        request = dict(request)
        with dev._lock:
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
        self.clear()
        if pending['device'] is not dev or self.clock() >= pending['expires']:
            raise ValueError("Review expired or connection changed. Review again.")
        with dev._lock:
            slots, context, _ = pedal.preflight(dev, **pending['request'])
            if digest([slots, context]) != pending['stamp']:
                raise ValueError("Device state changed after review. Nothing sent; review again.")
            result = pedal.execute(dev, [pending['request']], expected_preset=pending['preset'],
                                   external_audio_muted=True)
            result['results'] = [asdict(r) for r in result['results']]
            return result
