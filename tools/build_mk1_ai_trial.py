"""Immutable, audited source package for the separate experimental AI trial."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from tools.mk1_ai_trial import VERSION
from tools.release_audit import inspect_blob

ROOT = Path(__file__).resolve().parents[1]


def build(destination=None):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT).strip():
        raise ValueError('Commit the tested public source before building')
    archive = subprocess.check_output(['git', 'archive', '--format=zip', revision], cwd=ROOT)
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for item in source.infolist():
            if item.is_dir():
                continue
            name, data = item.filename, source.read(item)
            if name.startswith('/') or '..' in Path(name).parts or '\\' in name or inspect_blob(name, data):
                raise ValueError('Unsafe/private source member')
            files[name] = data
    required = {'tools/mk1_ai_trial.py', 'devices/axefx3/mk1_trial.py',
        'packaging/mk1-ai/index.html', 'packaging/mk1-ai/trial.js',
        'Install-MK1-AI-Trial.cmd', 'Start-MK1-AI-Trial.cmd',
        'docs/MK1-AI-TRIAL.md', 'tests/test_mk1_ai_trial.py'}
    if not required <= files.keys():
        raise ValueError('Incomplete trial source')
    manifest = dict(version=VERSION, source_commit=revision, experimental=True,
        mk1_hardware_accepted=False, permanent_storage=False,
        files={name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())})
    files['MK1-AI-PACKAGE.json'] = json.dumps(manifest, indent=2).encode('utf-8')
    folder = Path(destination or ROOT/'dist')
    folder.mkdir(parents=True, exist_ok=True)
    stem = 'ToneCommand-MK1-AI-Trial-'+VERSION
    path = folder/(stem+'.zip')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            bundle.writestr(stem+'/'+name, data)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix('.sha256').write_text(digest+'  '+path.name+'\n', encoding='ascii')
    print(json.dumps(dict(path=str(path), sha256=digest, source_commit=revision,
                         experimental=True, mk1_hardware_accepted=False)))
    return path


if __name__ == '__main__':
    build()
