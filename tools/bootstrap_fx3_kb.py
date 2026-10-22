"""Create a local evidence-derived KB on a fresh source checkout.

No account, MIDI, network, AI, original maintainer-private KB or model access.
Never replace an existing KB. Public documents are the portable source of facts.
"""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]


def bootstrap(root=ROOT):
    root=Path(root).resolve()
    target=root/'kb'
    if target.exists() and any(target.iterdir()):
        raise ValueError('KB already contains files; preserve it and reconcile evidence manually')
    ignored=subprocess.run(['git','check-ignore','-q','kb/INDEX.md'],cwd=root,check=False)
    tracked=subprocess.run(['git','ls-files','--','kb'],cwd=root,capture_output=True,check=True)
    if ignored.returncode != 0 or tracked.stdout.strip():
        raise ValueError('The local kb/ must be gitignored and untracked first')
    manifest=json.loads((root/'config/axefx3_upstream.json').read_text(encoding='utf-8'))
    # Require reviewed public references, not credentials or private captures.
    for name in ('FW33-COMPATIBILITY.md','AFX3-UPSTREAM-MAINTENANCE.md'):
        if not (root/'docs'/name).is_file():
            raise ValueError('Reviewed public compatibility/maintenance references are missing')
    files={
        'INDEX.md': '# Local evidence-derived knowledge base\n\n'
                    'Read index.json, always_load and matching topics before changes.\n'
                    'This is not the upstream maintainer private KB. Public compatibility\n'
                    'documents are facts, not new hardware acceptance. No secrets here.\n',
        'index.json': json.dumps(dict(always_load=['ALWAYS.md'],topics=[
            dict(topics=['upstream','integration','maintenance','release'],files=['UPSTREAM.md']),
            dict(topics=['axefx3','firmware','fw33','nam','tone3000','protocol'],files=['AFX3-FW33-NAM.md']),
            dict(topics=['hardware','midi','testing'],files=['HARDWARE_RULES.md'])]),indent=2)+'\n',
        'ALWAYS.md': '# Invariants\n\nNo current hardware, external mute or target permission is assumed.\n'
                    'One MIDI owner. Never widen Store/CAB/NAM allowlists or change the\n'
                    'never-brick guard. Preserve user settings and uncommitted work.\n'
                    'Unknown behavior fails closed. Source tests do not prove hardware.\n'
                    'Read AGENTS.md and public docs before changes. No Handsoff lane\n'
                    'has been established by this bootstrap. No account/model files in Git.\n',
        'UPSTREAM.md': '# Update provenance\n\n'
                       f"Audited upstream: {manifest['audited_commit']} ({manifest['audited_version']}).\n"
                       f"Source foundation: {manifest['integration_foundation']}.\n"
                       f"Status: {manifest['integration_status']}.\n"
                       'Read docs/AFX3-UPSTREAM-MAINTENANCE.md for update/publication gates.\n'
                       'Shared planner/UI remain upstream-owned; FX3 writes stay isolated.\n'
                       'Audited, integrated, deployed, remotely tested and hardware accepted\n'
                       'are separate states. Reconcile this file after each accepted update.\n',
        'AFX3-FW33-NAM.md': '# Exact compatibility evidence\n\n'
                           'Read docs/FW33-COMPATIBILITY.md fully before protocol changes.\n'
                           'Exact identity, declared MK2, measured numeric domains and the\n'
                           'NAM route are mandatory. NAM effect206 is not Chorus78.\n'
                           'Windows native slots001-256 install is separately permanent.\n'
                           'Read occupancy, suggest first free, require explicit slot choice.\n'
                           'Preset capture selection uses separately measured ordinals001-256;\n'
                           'hardware replay covered001/250/256, not every slot individually.\n'
                           'Route exploration compares AMP/CAB and NAM without enabling\n'
                           'unknown FW33 models, routing or controller writes. Full\n'
                           '65536-byte readback and private recovery export are required.\n'
                           'TONE3000 tokens never enter AI prompts, logs or Git. Account\n'
                           'selection does not authorize install, SEND or preset Store.\n'
                           'Historical owner listening acceptance does not accept a new port.\n',
        'HARDWARE_RULES.md': '# Hardware acceptance ladder\n\n'
                             'No hardware operations are authorized by bootstrapping a KB.\n'
                             '0. Offline synthetic protocol, API, GUI and validation tests.\n'
                             '1. Fresh power/mute/target permission and read-only exact identity.\n'
                             '2. Explicitly authorized writes with independent settled readback.\n'
                             '3. Independent Axe-Edit comparison after releasing TC MIDI.\n'
                             '4. Separate NAM overwrite or preset Store consent and verification.\n'
                             '5. Low physical volume user audition and physical pedal check.\n'
                             'Never automatically retry an unknown write or reload/restore.\n'
                             'Levels are conservative settings, not a physical audio limiter.\n'
                             'Record exact build/firmware and results; CI is not hardware.\n',
    }
    target.mkdir(exist_ok=True)
    for name,content in files.items():
        # Exclusive creation makes concurrent runs fail instead of overwriting.
        with (target/name).open('x',encoding='utf-8') as stream:stream.write(content)
    return target


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        target=bootstrap()
    except (ValueError,OSError,subprocess.CalledProcessError,json.JSONDecodeError) as exc:
        print(f'KB not created: {exc}')
        return 2
    print(f'Created local-only KB: {target}. No hardware or account accessed.')
    return 0


if __name__=='__main__':raise SystemExit(main())
