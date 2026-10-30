"""Build a versioned public-source MK1 evaluation ZIP, never from working files."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

from tools.mk1_tester import VERSION
from tools.release_audit import inspect_blob

ROOT = Path(__file__).resolve().parents[1]


def build(ref='HEAD', destination=None):
    revision = subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', ref+'^{commit}'], cwd=ROOT).decode().strip()
    archive = subprocess.check_output(['git', 'archive', '--format=zip', revision], cwd=ROOT)
    files = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for entry in source.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            if name.startswith('/') or '..' in Path(name).parts or '\\' in name:
                raise ValueError('Unsafe archive member')
            data = source.read(entry)
            if inspect_blob(name, data):
                raise ValueError(f'Refused private/secret artifact: {name}')
            files[name] = data
    required = {'tools/mk1_tester.py', 'tests/test_mk1_tester.py',
        'docs/MK1-TESTER-GUIDE.md', 'packaging/mk1/welcome.html',
        'packaging/mk1/Install.ps1', 'packaging/mk1/Start.ps1',
        'packaging/mk1/example_scenario.py', 'packaging/mk1/SCENARIO-CHECKLIST.txt',
        'Install-MK1.cmd', 'Start-MK1.cmd', 'MK1-Tester.code-workspace',
        'pyproject.toml', 'server.py', 'LICENSE', 'START-HERE-MK1.txt'}
    if not required <= files.keys():
        raise ValueError('Commit the complete tested kit before building it')
    # Exported source has no .git. This file carries its exact provenance.
    manifest = dict(version=VERSION, source_commit=revision, read_only=True,
        mk1_hardware_accepted=False,
        files={name:hashlib.sha256(data).hexdigest() for name,data in sorted(files.items())})
    files['MK1-PACKAGE.json'] = json.dumps(manifest,indent=2).encode('utf-8')
    output = Path(destination or ROOT / 'dist')
    output.mkdir(parents=True, exist_ok=True)
    stem = 'ToneCommand-MK1-Tester-'+VERSION
    path = output / (stem+'.zip')
    if path.exists():
        raise FileExistsError('Refusing to overwrite an existing test package')
    with zipfile.ZipFile(path, 'x', compression=zipfile.ZIP_DEFLATED) as package:
        for name, data in sorted(files.items()):
            package.writestr(stem+'/'+name, data)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    # Generated integrity artifact, not a source edit.
    (output / (stem+'.sha256')).write_text(checksum+'  '+path.name+'\n',encoding='ascii')
    print(json.dumps(dict(path=str(path),sha256=checksum,source_commit=revision,
        files=len(files),size=path.stat().st_size,read_only=True)))
    return path


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ref',default='HEAD')
    parser.add_argument('--destination')
    args=parser.parse_args()
    build(args.ref,args.destination)
