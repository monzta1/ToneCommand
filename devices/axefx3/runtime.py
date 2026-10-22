"""Read-only identity of this running checkout, pinned when the app registers.

Not firmware evidence, an update service, account data or a hardware operation.
"""
import hashlib
import os
from pathlib import Path
import subprocess
from fm9.paths import project_root

CONTRACT = 'fx3-workspace-20261012'
FILES = ('server.py', 'fm9/planner.py', 'fm9/protocol.py', 'fm9/device.py',
         'fm9/language.py', 'ui/languages/i18next.min.js', 'ui/languages/tc-language.js',
         'ui/languages/en.json', 'ui/languages/template.json', 'ui/languages/manifest.json',
         'ui/axefx3.js', 'ui/axefx3.html', 'ui/index.html',
         'devices/axefx3/data/fw33_amp_models.json',
         'devices/axefx3/data/fw33_cab_models.json',
         'devices/axefx3/data/fw33_cab_probe.json',
         'devices/axefx3/data/fw33_drive_probe.json',
         'devices/axefx3/data/fw33_effect_calibration.json',
         'devices/axefx3/data/fw33_zero_tempo_calibration.json',
         'devices/axefx3/data/fw33_inherited_controls.json',
         'devices/axefx3/data/fw33_legacy_zeros.json',
         'devices/axefx3/data/fw33_effect_models.json') + tuple(
    'devices/axefx3/' + path.name
    for path in sorted(Path(__file__).resolve().parent.glob('*.py')))


def identity(root=None):
    root = Path(root or project_root()).resolve()
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
              for name in FILES}
    revision = ''
    try:
        result = subprocess.run(['git', '-C', str(root), 'rev-parse', '--short', 'HEAD'],
                                capture_output=True, timeout=2, check=False)
        if result.returncode == 0:
            revision = result.stdout.decode('ascii', errors='strict').strip()
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass  # An exported checkout remains identifiable by its file hashes.
    return dict(contract=CONTRACT, source_root=str(root), pid=os.getpid(),
                revision=revision, files=hashes)
