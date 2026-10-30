"""Native conversion for the ONE measured A2 profile, not arbitrary NAMs.

Independent reference: Axe-Edit 1.15.01's upstream A2 conversion/export.
The full 64 KiB image and 130 outgoing frames reproduce that export exactly.
No editor, executable, downloaded code or model inference is involved.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import struct

from fm9 import protocol as p
from .nam_memory import parse_export
from . import nam_slots

SIZE = 65536
WEIGHT_COUNTS = (1871, 12146)
DILATIONS = [1, 3, 7, 17, 41, 101, 239] * 2 + [1, 13] + [1, 3, 7, 17, 41, 101, 239]
KERNELS = [6] * 14 + [15, 15] + [6] * 7


class NamFileError(ValueError):
    pass


def layer_config(channels):
    layer = dict(input_size=1, condition_size=1,
                 head=dict(out_channels=1, kernel_size=16, bias=True),
                 channels=channels, kernel_sizes=KERNELS, dilations=DILATIONS,
                 activation=[dict(type='LeakyReLU', negative_slope=.01) for _ in DILATIONS],
                 bottleneck=channels, head1x1=dict(active=False, out_channels=1, groups=1),
                 layer1x1=dict(active=True, groups=1), groups_input=1, groups_input_mixin=1,
                 gating_mode=['none'] * len(DILATIONS),
                 secondary_activation=[None] * len(DILATIONS), slimmable=None)
    for key in ('conv_pre_film', 'conv_post_film', 'input_mixin_pre_film',
                'input_mixin_post_film', 'activation_pre_film', 'activation_post_film',
                'layer1x1_post_film', 'head1x1_post_film'):
        layer[key] = dict(active=False, shift=True, groups=1)
    return layer


def _float(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise NamFileError(f'{label} must be a finite number.')
    try:
        if not math.isfinite(value):
            raise NamFileError(f'{label} must be a finite number.')
        packed = struct.pack('<f', value)
    except (OverflowError, struct.error):
        raise NamFileError(f'{label} exceeds the float32 domain.') from None
    if not math.isfinite(struct.unpack('<f', packed)[0]):
        raise NamFileError(f'{label} exceeds the float32 domain.')
    return packed


@dataclass(frozen=True)
class CompiledNAM:
    name: str
    payload: bytes
    source_sha256: str
    source: bytes

    @property
    def payload_sha256(self):
        return hashlib.sha256(self.payload).hexdigest()

    def frames(self, slot=1):
        """Encode one confirmed address; this does not authorize transmission."""
        nam_slots.number(slot)
        words = struct.unpack('<16384I', self.payload)
        frames = [p.envelope(0x54, nam_slots.header(slot), model=16)]
        checksum = 0
        for start in range(0, len(words), 128):
            data = [0, 1]
            for word in words[start:start + 128]:
                checksum ^= word
                data.extend((word >> (7 * i)) & 127 for i in range(5))
            frames.append(p.envelope(0x55, data, model=16))
        frames.append(p.envelope(0x56, [(checksum >> (7 * i)) & 127 for i in range(5)], model=16))
        capture = parse_export(frames,slot=slot)
        if capture.name != self.name or capture.payload_sha256 != self.payload_sha256:
            raise NamFileError('Compiled NAM frame validation failed.')
        return tuple(bytes(frame) for frame in frames)


def compile_nam(raw: bytes, name: str) -> CompiledNAM:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 4 * 1024 * 1024:
        raise NamFileError('NAM source size is outside the supported limit.')
    if (not isinstance(name, str) or not 1 <= len(name) <= 27
            or any(not 32 <= ord(c) <= 126 for c in name)
            or name.strip().upper() in ('EMPTY', '<EMPTY>') or name != name.strip()):
        raise NamFileError('Capture name must be 1–27 printable ASCII characters, not EMPTY.')
    try:
        model = json.loads(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise NamFileError('Not a valid NAM JSON file.') from None
    if (not isinstance(model, dict) or model.get('version') != '0.7.0'
            or model.get('architecture') != 'SlimmableContainer' or model.get('sample_rate') != 48000
            or model.get('weights')):
        raise NamFileError('Only the measured 48 kHz A2 SlimmableContainer v0.7.0 profile is supported.')
    config = model.get('config')
    if not isinstance(config, dict) or set(config) != {'submodels'}:
        raise NamFileError('Unsupported A2 container configuration.')
    submodels = config['submodels']
    if not isinstance(submodels, list) or len(submodels) != 2:
        raise NamFileError('The measured A2 profile requires two submodels.')
    payload = bytearray(SIZE)
    payload[:len(name)] = name.encode('ascii')
    struct.pack_into('<I', payload, 28, 0x60000000)
    metadata = model.get('metadata', {})
    if not isinstance(metadata, dict):
        raise NamFileError('NAM metadata must be an object.')
    offset = 256
    for field in ('loudness', 'gain', 'input_level_dbu', 'output_level_dbu'):
        value = metadata.get(field)
        if value is None:
            packed = struct.pack('<I', 0x7fc00000)  # observed absent-calibration sentinel
        else:
            packed = _float(value, field)
            if field == 'gain' and not 0 < value <= 100:
                raise NamFileError('Capture gain calibration is outside the supported range.')
            if field == 'loudness' and not -150 <= value <= 0:
                raise NamFileError('Capture loudness calibration is outside the supported range.')
            if field.endswith('_dbu') and not -100 <= value <= 100:
                raise NamFileError('Capture level calibration is outside the supported range.')
        payload[offset:offset + 4] = packed
        offset += 4
    for i, sub in enumerate(submodels):
        if (not isinstance(sub, dict) or set(sub) != {'max_value', 'model'}
                or isinstance(sub['max_value'], bool) or sub['max_value'] != (.5, 1)[i]):
            raise NamFileError('Unsupported A2 submodel selector.')
        net = sub['model']
        if (not isinstance(net, dict) or net.get('version') != '0.7.0'
                or net.get('architecture') != 'WaveNet' or net.get('sample_rate') != 48000):
            raise NamFileError('Unsupported A2 submodel architecture or sample rate.')
        cfg = net.get('config')
        if (not isinstance(cfg, dict) or set(cfg) != {'layers', 'head', 'head_scale'}
                or cfg['head'] is not None or cfg['layers'] != [layer_config((3, 8)[i])]
                or json.dumps(cfg['layers'], sort_keys=True) != json.dumps([layer_config((3, 8)[i])], sort_keys=True)):
            raise NamFileError('A2 layer layout differs from the independently measured profile.')
        scale = _float(cfg['head_scale'], 'head_scale')
        if not 0 < cfg['head_scale'] <= 1:
            raise NamFileError('Unsupported A2 head scale.')
        weights = net.get('weights')
        if not isinstance(weights, list) or len(weights) != WEIGHT_COUNTS[i]:
            raise NamFileError('A2 weight count differs from the measured profile.')
        packed = b''.join(_float(value, 'weight') for value in weights)
        if packed[-4:] != scale:
            raise NamFileError('A2 final weight does not match the declared head scale.')
        payload[offset:offset + len(packed)] = packed
        offset += len(packed)
    # Ten unused calibration values in the measured format, then zero padding.
    payload[offset:offset + 40] = struct.pack('<10I', *([0x7fc00000] * 10))
    compiled = CompiledNAM(name, bytes(payload), hashlib.sha256(raw).hexdigest(), raw)
    compiled.frames()  # a malformed header/checksum must fail before any MIDI
    return compiled
