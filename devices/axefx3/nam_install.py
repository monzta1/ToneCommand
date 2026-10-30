"""Two-phase native NAM installation. No Axe-Edit, shell or global guard changes.

Only the measured Windows/MK2/FW33/A2 combination is supported, slots001-256.
Read-only preview binds source, preset, device profile and old memory hash.
Commit requires distinct mute, flash-write and overwrite acknowledgements.
Every commit saves a full recovery SysEx outside the checkout before writing.
"""
import json
import os
from pathlib import Path
import secrets
import threading
import time
import re
import unicodedata

from . import fw33_profile, nam_file, nam_slots, tone3000 as t3


def _platform_supported():
    return os.name == 'nt'


def capture_name(source_name, model_id):
    """Map catalog labels to the measured header, without relaxing the compiler.

    The original catalog name remains visible in preview. This changes only
    the capture label, never weights, calibration, architecture or slot.
    """
    if not isinstance(source_name,str) or type(model_id) is not int or model_id<=0:
        raise nam_file.NamFileError('Invalid source capture identity.')
    ascii_name=unicodedata.normalize('NFKD',source_name).encode('ascii','ignore').decode('ascii')
    ascii_name=re.sub(r'[^ -~]',' ',ascii_name)
    name=' '.join(ascii_name.split())[:27].rstrip()
    return name if name and name.upper() not in {'EMPTY','<EMPTY>'} else f'NAM {model_id}'[:27]


class Installer:
    def __init__(self, device_lock, get_device, policy):
        self.device_lock, self.get_device, self.policy = device_lock, get_device, policy
        self.lock = threading.RLock()
        self.pending = None

    def capability(self):
        policy = self.policy()
        enabled = (_platform_supported() and policy.get('device') == 'axe-fx-iii'
                   and policy.get('firmware') == fw33_profile.KEY and policy.get('variant') == 'mk2'
                   and not policy.get('simulated'))
        return {'installation_supported': enabled, 'slot_range': [1,256], 'native': True,
                'scope': 'Measured A2 profile, Windows, Axe-Fx III MK2, exact FW33 beta, NAM slots001-256. Explicit target confirmation required.',
                'reason': '' if enabled else 'NAM installation requires the measured MK2/FW33 Windows profile. FM9/MK1 are not supported.'}

    def inventory(self):
        with self.lock, self.device_lock:
            self.pending = None
            if not self.capability()['installation_supported']:
                raise t3.ToneError(self.capability()['reason'],422)
            device = self.get_device()
            try:
                rows = device.scan_nam_slots()
            except (ValueError,RuntimeError,OSError) as exc:
                raise t3.ToneError(str(exc),409) from None
            if len(rows) != 256 or [row.slot for row in rows] != list(range(1,257)):
                raise t3.ToneError('Incomplete NAM inventory. No slot will be assumed empty.',409)
            return dict(slots=[dict(slot=r.slot,name=r.name,occupied=r.occupied) for r in rows],
                        first_available=next((r.slot for r in rows if not r.occupied),None),
                        complete=True,readonly=True,
                        note='Choose the destination explicitly. Inventory is a current reading, not a reservation.')

    def _device(self, expected_preset):
        if not self.capability()['installation_supported']:
            raise t3.ToneError(self.capability()['reason'], 422)
        policy = self.policy()
        if policy.get('gig_locked'):
            raise t3.ToneError('GIG LOCK is on. No NAM memory write allowed.', 423)
        if expected_preset not in policy.get('allowed_presets', ()):
            raise t3.ToneError('Choose an explicitly allowed empty test preset before NAM installation.', 403)
        device = self.get_device()
        if (device.model != 16 or getattr(device, '_injected_ports', True)
                or device.firmware_label() != fw33_profile.KEY):
            raise t3.ToneError('Fresh device identity does not match the measured NAM profile.', 422)
        preset = device.current_preset()
        if not preset or preset[0] != expected_preset:
            raise t3.ToneError('The target preset changed. Prepare the NAM installation again.', 409)
        grid = device.read_grid()
        if grid is None or any(cell.effect_id for cell in grid):
            raise t3.ToneError('Use an empty test preset so installation cannot replace an audible active capture.', 422)
        return device

    def prepare(self, model_id, expected_preset, slot):
        try:
            nam_slots.number(slot)
        except ValueError as exc:
            raise t3.ToneError(str(exc),422) from None
        with self.lock:
            self.pending = None
        # Nothing sent while downloading/parsing creator-controlled content.
        selected = t3.client.status().get('selected')
        if not selected or not selected.get('model') or selected['model']['id'] != model_id:
            raise t3.ToneError('Select the exact NAM model in TC before preparing installation.', 409)
        raw, _filename = t3.client.download(model_id)
        try:
            source_name=selected['model']['name']
            compiled = nam_file.compile_nam(raw, capture_name(source_name,model_id))
        except nam_file.NamFileError as exc:
            raise t3.ToneError(str(exc), 422) from None
        with self.lock, self.device_lock:
            device = self._device(expected_preset)
            before = device.read_nam_slot(slot)
            if before.slot != slot or before.byte_count != 65536:
                raise t3.ToneError('Full readback of the selected NAM slot is required.',422)
            token = secrets.token_urlsafe(32)
            self.pending = dict(token=token, expires=time.monotonic() + 600, compiled=compiled,
                                before=before, device=device, expected_preset=expected_preset,
                                model_id=model_id, tone_id=selected['tone']['id'],slot=slot)
            return {'prepared_id': token, 'readonly': True, 'slot': slot, 'name': compiled.name,
                    'source_name':source_name,'name_adjusted':compiled.name!=source_name,
                    'existing_name': before.name, 'existing_sha256': before.payload_sha256,
                    'existing_occupied': not before.empty,
                    'source_sha256': compiled.source_sha256, 'payload_sha256': compiled.payload_sha256,
                    'payload_bytes': len(compiled.payload), 'expected_preset': expected_preset,
                    'permanent': True, 'expires_seconds': 600,
                    'detail': f'Nothing installed. Confirm external mute and permanent writing to NAM slot{slot:03d}. No automatic preset capture selection.'}

    def commit(self, prepared_id, muted, flash, overwrite):
        if muted is not True or flash is not True or overwrite is not True:
            raise t3.ToneError('Confirm external mute, permanent NAM memory write and slot replacement.', 403)
        with self.lock, self.device_lock:
            pending = self.pending
            if (not pending or not secrets.compare_digest(str(prepared_id), pending['token'])
                    or pending['expires'] < time.monotonic()):
                raise t3.ToneError('NAM preview expired or changed. Prepare installation again.', 409)
            # One-use even on failure. No automatic retry of a persistent write.
            self.pending = None
            selected = t3.client.status().get('selected')
            if (not selected or not selected.get('model')
                    or selected['model']['id'] != pending['model_id']
                    or selected['tone']['id'] != pending['tone_id']):
                raise t3.ToneError('The selected capture changed. Nothing sent; prepare again.', 409)
            device = self._device(pending['expected_preset'])
            if device is not pending['device']:
                raise t3.ToneError('Device connection changed after preview. Nothing installed.',409)
            slot = pending['slot']
            before, frames = device.export_nam_slot(slot)
            if before != pending['before']:
                raise t3.ToneError(f'Slot{slot:03d} changed after preview. Nothing sent; prepare again.', 409)
            backup = self._backup(before, frames)
            # Front-panel changes are not serialized by the server lock.
            # Recheck the target after exporting/saving the recovery image.
            self._device(pending['expected_preset'])
            try:
                with device.edit_session(external_audio_muted=True,
                                         expected_preset=pending['expected_preset']):
                    device._nam_install_permit = (slot,pending['compiled'].source_sha256,before.payload_sha256)
                    try:
                        after = device.install_nam_slot(slot,pending['compiled'],before.payload_sha256)
                    finally:
                        device._nam_install_permit = None
            except Exception:
                raise t3.ToneError('NAM installation/readback failed. Keep audio muted. '
                                   f'Recovery backup: {backup}. Nothing retried or stored as a preset.', 502) from None
            result = {'ok': True, 'installed': True, 'name': after.name, 'slot': slot,
                      'payload_sha256': after.payload_sha256, 'bytes_verified': after.byte_count,
                      'firmware': fw33_profile.KEY, 'backup': str(backup),
                      'preset_stored': False, 'audio_verified': False}
            if (after.slot != slot or after.empty or after.payload_sha256 != pending['compiled'].payload_sha256
                    or after.name != pending['compiled'].name or after.byte_count != 65536):
                raise t3.ToneError(f'NAM readback mismatch. Recovery backup: {backup}. Keep audio muted.', 502)
        # The unit is verified even if account metadata cannot be persisted.
        try:
            with t3.client.lock:
                session = t3.client._session()
                current = session.get('selected')
                if (current and current.get('model', {}).get('id') == pending['model_id']
                        and current['tone']['id'] == pending['tone_id']):
                    current.update(installed=True, compatibility_verified=True, installation=result)
                    t3.client._save_session(session)
        except Exception:
            result['warning'] = 'Hardware installation verified, but local account metadata could not be saved.'
        return result

    @staticmethod
    def _backup(capture, frames):
        from .nam_memory import parse_export
        try:
            check = parse_export(frames,slot=capture.slot,allow_empty=True)
        except ValueError:
            raise t3.ToneError('Recovery export did not validate. Nothing installed.', 422) from None
        if check != capture:
            raise t3.ToneError('Recovery export did not validate. Nothing installed.', 422)
        root = os.getenv('TONECOMMAND_NAM_BACKUP_DIR', '')
        directory = (Path(root) if root else Path.home() / '.tonecommand' / 'nam-backups').resolve()
        checkout = Path(__file__).resolve().parents[2]
        if directory == checkout or checkout in directory.parents:
            raise t3.ToneError('Persistent recovery backups must be outside the project.', 422)
        filename = directory / (f'slot{capture.slot:03d}-before-' + secrets.token_hex(12) + '.syx')
        try:
            t3._write_private(filename, b''.join(bytes(frame) for frame in frames))
            stored = filename.read_bytes()
            if stored != b''.join(bytes(frame) for frame in frames):
                raise OSError('Backup compare failed')
            t3._write_private(filename.with_suffix('.json'), json.dumps({
                'slot': capture.slot, 'name': capture.name, 'payload_sha256': capture.payload_sha256,
                'firmware': fw33_profile.KEY, 'byte_count': capture.byte_count}).encode('utf8'))
        except OSError:
            raise t3.ToneError('Recovery backup could not be saved and verified. Nothing installed.', 500) from None
        return filename
