"""Synthetic model data only; no live network, editor or MIDI."""
from dataclasses import replace
import json
from pathlib import Path
import threading
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from devices.axefx3 import nam_file, nam_install, nam_memory, fw33_profile, tone3000 as t3
from devices.axefx3.adapter import AxeFxIII
from fm9 import protocol as p
import server


def source():
    submodels = []
    for i, channels in enumerate((3, 8)):
        weights = [0.] * nam_file.WEIGHT_COUNTS[i]
        weights[-1] = .01
        submodels.append({'max_value': (.5, 1)[i], 'model': {
            'architecture': 'WaveNet', 'version': '0.7.0', 'sample_rate': 48000,
            'config': {'layers': [nam_file.layer_config(channels)], 'head': None, 'head_scale': .01},
            'weights': weights}})
    return {'architecture': 'SlimmableContainer', 'version': '0.7.0', 'sample_rate': 48000,
            'config': {'submodels': submodels}, 'metadata': {'loudness': -20, 'gain': .5}}


def compile_source(name='Synthetic'):
    return nam_file.compile_nam(json.dumps(source()).encode(), name)


def test_converter_full_roundtrip_and_measured_geometry():
    compiled = compile_source()
    frames = compiled.frames()
    capture = nam_memory.parse_export(frames)
    assert len(compiled.payload) == 65536 and len(frames) == 130
    assert frames[0] == bytes(p.envelope(0x54, [0, 0, 0, 0, 0, 1], model=16))
    assert all(len(f) == 650 and f[6:8] == bytes([0, 1]) for f in frames[1:-1])
    assert capture.name == 'Synthetic' and capture.payload_sha256 == compiled.payload_sha256


@pytest.mark.parametrize('fault', ['arch', 'version', 'rate', 'selector', 'layer', 'weights',
                                 'nan', 'inf', 'huge_int', 'bool', 'layer_bool', 'scale', 'meta', 'loudness', 'gain'])
def test_unmeasured_or_unsafe_source_is_refused(fault):
    model = source()
    net = model['config']['submodels'][0]['model']
    if fault == 'arch': model['architecture'] = 'LSTM'
    if fault == 'version': model['version'] = '1.0.0'
    if fault == 'rate': model['sample_rate'] = 44100
    if fault == 'selector': model['config']['submodels'][1]['max_value'] = True
    if fault == 'layer': net['config']['layers'][0]['channels'] = 4
    if fault == 'weights': net['weights'].pop()
    if fault == 'nan': net['weights'][0] = float('nan')
    if fault == 'inf': net['weights'][0] = 1e100
    if fault == 'huge_int': net['weights'][0] = 10 ** 1000
    if fault == 'bool': net['weights'][0] = True
    if fault == 'layer_bool': net['config']['layers'][0]['groups_input'] = True
    if fault == 'scale': net['config']['head_scale'] = .2
    if fault == 'meta': model['metadata'] = []
    if fault == 'loudness': model['metadata']['loudness'] = 20
    if fault == 'gain': model['metadata']['gain'] = 0
    with pytest.raises(nam_file.NamFileError):
        nam_file.compile_nam(json.dumps(model).encode(), 'Synthetic')


@pytest.mark.parametrize('name', ['', 'x' * 28, 'EMPTY', '<EMPTY>', 'hé', ' bad', 'bad\n'])
def test_name_refusals(name):
    with pytest.raises(nam_file.NamFileError):
        nam_file.compile_nam(json.dumps(source()).encode(), name)
