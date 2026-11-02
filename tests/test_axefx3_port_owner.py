"""Real OS lease, fake MIDI only, including a separate process contender."""
from pathlib import Path
import subprocess
import sys

import pytest

from devices.axefx3 import port_owner
from devices.axefx3.adapter import AxeFxIII
from devices.axefx3.live_observation import LiveReader
from fm9 import midi_transport
from fm9.device import FM9NotFound
from tests.test_axefx3_live_observation import ObservationPorts


@pytest.fixture
def owner_file(tmp_path,monkeypatch):
    path=tmp_path/'exclusive.lock'
    monkeypatch.setattr(port_owner,'_lock_path',lambda:path)
    return path


def test_app_must_release_both_ports_before_reader_opens(owner_file,monkeypatch):
    opened=[]
    def opening(*args):
        pair=ObservationPorts();opened.append(pair);return pair.inp,pair.outp
    monkeypatch.setattr(midi_transport,'open_ports',opening)
    app=AxeFxIII()
    try:
        with pytest.raises(FM9NotFound,match='owner|owned'):
            LiveReader()
        assert len(opened)==1 and not opened[0].closes
    finally:app.close()
    assert opened[0].closes==['in','out']
    reader=LiveReader()
    try:assert len(opened)==2
    finally:reader.close()


def test_failed_backend_open_releases_lease(owner_file,monkeypatch):
    def fail(*args):raise midi_transport.TransportError('fake open failed')
    monkeypatch.setattr(midi_transport,'open_ports',fail)
    with pytest.raises(midi_transport.TransportError):LiveReader()
    lease=port_owner.acquire();lease.close()


def test_failed_initial_read_closes_pair_and_releases_lease(owner_file,monkeypatch):
    pair=ObservationPorts();pair.transform=lambda frame,packets:[]
    monkeypatch.setattr(midi_transport,'open_ports',lambda *a:(pair.inp,pair.outp))
    monkeypatch.setattr(AxeFxIII,'firmware_label',lambda self:'')
    with pytest.raises(FM9NotFound):LiveReader()
    assert pair.closes==['in','out']
    lease=port_owner.acquire();lease.close()


@pytest.mark.parametrize('failed_port',['in','out'])
def test_uncertain_close_does_not_hand_ownership_to_second_reader(owner_file,monkeypatch,failed_port):
    pair=ObservationPorts()
    monkeypatch.setattr(midi_transport,'open_ports',lambda *a:(pair.inp,pair.outp))
    reader=LiveReader()
    def fail():raise OSError('fake uncertain close')
    (pair.inp if failed_port=='in' else pair.outp).close=fail
    try:
        with pytest.raises(OSError):reader.close()
        with pytest.raises(FM9NotFound):port_owner.acquire()
    finally:reader._port_lease.close()  # Fake ports only; explicit test teardown.


def test_another_process_cannot_acquire_until_normal_handoff(owner_file):
    code='''
import sys
from pathlib import Path
from devices.axefx3 import port_owner
from fm9.device import FM9NotFound
port_owner._lock_path=lambda:Path(sys.argv[1])
try:lease=port_owner.acquire()
except FM9NotFound:raise SystemExit(23)
else:lease.close()
'''
    def child():
        return subprocess.run([sys.executable,'-c',code,str(owner_file)],
            cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=30)
    lease=port_owner.acquire()
    try:assert child().returncode==23
    finally:lease.close()
    result=child();assert result.returncode==0,result.stderr
