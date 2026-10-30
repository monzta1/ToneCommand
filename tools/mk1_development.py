"""Explicit source-checkout launcher, not a validated MK1 release or MIDI unlock.

Allows local edits at startup. Pins that source until normal shutdown/restart.
This is provenance/drift detection for a trusted developer, not a sandbox or
protection against deliberately modifying the guard itself.
"""
from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    try:
        return subprocess.run(['git', *args], cwd=root, capture_output=True,
                              check=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        raise ValueError('Git source could not be identified; no hardware build permitted') from None


def identify(root):
    from tools.release_audit import private_path
    root = Path(root).resolve()
    if Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root:
        raise ValueError('Start from the root of a real Git clone, not a generic ZIP')
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    branch = git(root, 'branch', '--show-current').decode().strip() or 'detached HEAD'
    dirty = bool(git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=normal'))
    names = set(git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0')) - {b''}
    digest = hashlib.sha256()
    count = 0
    for raw in sorted(names):
        name = raw.decode('utf-8')
        if private_path(name):
            continue
        path = root/name
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Source symlinks or paths outside the checkout are not admitted')
        if path.is_dir():
            raise ValueError('Embedded repositories/submodules need separate provenance')
        data = hashlib.sha256(path.read_bytes()).digest() if path.exists() else b'DELETED'
        digest.update(raw+b'\0'+data+b'\0')
        count += 1
    return dict(source_commit=commit, source_branch=branch, source_dirty=dirty,
                source_digest=digest.hexdigest(), source_files=count,
                development=True, validated_release=False)


@dataclass(frozen=True)
class SourcePin:
    root: Path
    info: dict

    @classmethod
    def capture(cls, root=ROOT):
        root = Path(root).resolve()
        first = identify(root)
        if identify(root) != first:
            raise ValueError('Source changed during startup; finish editing and restart')
        return cls(root, first)

    def verify(self):
        if identify(self.root) != self.info:
            raise ValueError('Source changed after startup. Stop TC normally, restart, reconnect and review a NEW plan. Nothing automatically resent.')


def main():
    import struct
    import sys
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12) or struct.calcsize('P') != 8:
        raise SystemExit('Use Windows and 64-bit Python 3.12. No driver/firmware installation performed.')
    try:
        pin = SourcePin.capture()
        # Capture before importing the application, then check the loaded source.
        from tools import mk1_ai_trial
        pin.verify()
        mk1_ai_trial.configure()
        app = mk1_ai_trial.create_app(source_info=pin.info, check_source=pin.verify)
        print('UNOFFICIAL MK1 DEVELOPMENT | not a validated release')
        print(pin.info['source_branch'], pin.info['source_commit'],
              'MODIFIED' if pin.info['source_dirty'] else 'clean', pin.info['source_digest'])
        mk1_ai_trial.serve_app(app)
    except (ValueError, OSError) as error:
        raise SystemExit(str(error)) from None


if __name__ == '__main__':
    main()
