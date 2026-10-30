r"""Adapt the labels; use only the running read-only server.

Run from the package root with .venv\Scripts\python.exe. Do not add direct
MIDI/adapter calls or remove the server identity and read-only checks.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.mk1_tester import VERSION, request_local


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirm-monitoring-muted',action='store_true')
    parser.add_argument('--label',default='custom-baseline')
    args=parser.parse_args(argv)
    if not args.confirm_monitoring_muted:
        parser.error('Mute external monitoring, close Axe-Edit and confirm before observing.')
    status=request_local('/api/mk1-test/status')
    if status.get('version')!=VERSION or status.get('read_only') is not True or not status.get('connected'):
        parser.error('Connect through the matching read-only MK1 tester first.')
    result=request_local('/api/mk1-test/observe',dict(consent=True,label=args.label))
    # Deliberately print only the shareable summary, not the local grid/names.
    print(json.dumps(result['observation'],indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
