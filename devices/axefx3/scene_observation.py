"""Explicit muted original-scene survey, no channel/bypass assignment writes.

Complete observations and exact official identity are prerequisites. A scene
recall is a mutation, not a passive GET. Never silently restore after failure.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import threading
import time

import mido

from fm9.device import ReadOnly
from . import protocol
from .official_amp_writer import OfficialAmpWriter, _OfficialOutput


@dataclass(frozen=True)
class SceneRecall:
    number: int

    def __post_init__(self):
        if type(self.number) is not int or self.number not in range(1, 9):
            raise ValueError('An explicit scene number 1..8 is required')

    def frame(self):
        return protocol.envelope(1, [36, 0, 0, 0, 1, 0, self.number - 1,
                                      0, 0, 0, 0, 0, 0, 0, 0])


class _SceneOutput(_OfficialOutput):
    def __init__(self, port, chassis):
        super().__init__(port, chassis)
        self._scene_permit = None

    @contextmanager
    def _scene_once(self, recall):
        if type(recall) is not SceneRecall or self._scene_permit is not None or self._permit is not None:
            raise ReadOnly('One exact scene recall requires an idle output boundary')
        self._scene_permit = (threading.get_ident(), tuple(recall.frame()))
        try:
            yield
        finally:
            self._scene_permit = None

    def send(self, message):
        frame = message.bytes() if message.type == 'sysex' else []
        if self._scene_permit == (threading.get_ident(), tuple(frame)):
            self._scene_permit = None
            self.guard.check(frame[5])
            return self._port.send(mido.Message('sysex', data=frame[1:-1]))
        return super().send(message)


def recalled(before, after, number):
    """Only scene number and original block channel/bypass may differ."""
    wanted = deepcopy(before)
    if after['scene'] != number:
        raise ValueError('Recalled scene did not answer')
    old, new = wanted['status'], after['status']
    if [b['effect_id'] for b in old] != [b['effect_id'] for b in new]:
        raise ValueError('Scene recall changed block inventory')
    wanted['scene'] = number
    for previous, current in zip(old, new):
        previous['channel'], previous['bypassed'] = current['channel'], current['bypassed']
    if wanted != after:
        raise ValueError('Scene recall changed an unrequested parameter, model, modifier or route')


class SceneSurvey(OfficialAmpWriter):
    """Separate acceptance component; ordinary app registration is unchanged."""
    @staticmethod
    def _output(port, chassis):
        return _SceneOutput(port, chassis)

    def _recall(self, number, current):
        recall = SceneRecall(number)
        self._identity()
        if self.capture().data() != current:
            raise ReadOnly('Concurrent preset change before scene recall')
        if current['scene'] == number:
            return current
        success = False
        try:
            with self.outp._scene_once(recall):
                self._send(recall.frame())
            for _ in range(4):
                time.sleep(.15)
                after = self.capture().data()
                try:
                    recalled(current, after, number)
                except ValueError:
                    continue
                success = True
                return after
            raise ReadOnly('Scene recall could not be independently preserved; no retry')
        finally:
            if not success:
                self._uncertain = True

    def survey(self, expected_preset, *, external_audio_muted=False, target_confirmed=False):
        if (external_audio_muted is not True or target_confirmed is not True
                or type(expected_preset) is not int or expected_preset not in range(1024)):
            raise ReadOnly('Explicit current target and external mute required before scene recalls')
        with self._lock:
            self._review = None
            self._identity()
            initial = self.capture().data()
            if initial['preset'][0] != expected_preset:
                raise ReadOnly('Selected preset differs from the pinned survey target')
            current, maps = initial, []
            deadline = time.monotonic() + 120
            for number in range(1, 9):
                if time.monotonic() >= deadline:
                    self._uncertain = True
                    raise ReadOnly('Scene survey expired; no automatic restore')
                current = self._recall(number, current)
                maps.append(dict(scene=number, name=current['scenes'][number - 1][1],
                                 status=deepcopy(current['status'])))
            current = self._recall(initial['scene'], current)
            if current != initial or self.capture().data() != initial:
                self._uncertain = True
                raise ReadOnly('Original scene did not return unchanged; inspect without retry')
            return dict(state=initial, maps=maps, stored=False, parameter_writes=0,
                        scene_survey_verified=True, original_scene_returned=True)
