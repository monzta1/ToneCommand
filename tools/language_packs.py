"""Build/check English catalogs and public translation-only release ZIPs."""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.5.16-lang.1'
ASSETS = ('en.json', 'template.json', 'manifest.json')
PROTECTED = re.compile(r'\b(mute[ds]?|overwrite|permanent|firmware|safety|never|read.only|limiter|confirmation|readback|unsaved|discard|reviewed)\b|\bI confirm\b', re.I)
TECHNICAL = re.compile(r'^(?:External \d+|Axe-Fx III|FM[39]|MK[12]|NAM|Off|On|Fast Pos|dB|Hz|kHz|ms|BPM)$')


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = []
        self.keys = set()

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'textarea', 'pre', 'code'):
            self.skip.append(tag)
        if not self.skip:
            self.keys.update(v.strip() for k, v in attrs
                             if k in ('title', 'placeholder', 'aria-label') and v and v.strip())

    def handle_endtag(self, tag):
        if self.skip and self.skip[-1] == tag:
            self.skip.pop()

    def handle_data(self, data):
        key = data.strip()
        if not self.skip and key and re.search('[A-Za-z]', key):
            self.keys.add(key)


def source_keys(root=ROOT):
    root = Path(root)
    keys = set()
    for page in ('ui/index.html', 'ui/axefx3.html', 'ui/controllers.html', 'packaging/mk1/welcome.html'):
        if (root / page).exists():
            parser = Markup()
            parser.feed((root / page).read_text(encoding='utf-8'))
            keys.update(parser.keys)
    for script in ('ui/languages/tc-language.js', 'ui/axefx3.js', 'ui/controllers.js'):
        if not (root / script).exists():
            continue
        source = (root / script).read_text(encoding='utf-8')
        for literal in re.findall(r'\b(?:tr|tcText)\(("(?:[^"\\]|\\.)*")', source):
            value = json.loads(literal)
            if not value.lstrip().startswith('<'):
                keys.add(value)
        if script.endswith('tc-language.js'):
            # Fixed UI markup is part of the public catalog, never user data.
            for literal in re.findall(r"'((?:[^'\\]|\\.)*)'", source):
                if '<' in literal and '>' in literal:
                    parser = Markup()
                    parser.feed(literal)
                    keys.update(parser.keys)
            keys.update(('LANGUAGE', 'Interface language', 'Language pack imported. Missing entries use English.',
                         'Interface language changed. Existing plans and unsent input are unchanged.'))
    return {k for k in keys if k not in ('__proto__', 'constructor', 'prototype')}


def documents(root=ROOT):
    root = Path(root)
    path = root / 'ui/languages/en.json'
    previous = json.loads(path.read_text(encoding='utf-8'))['translations'] if path.exists() else {}
    # Keep older public keys so a growing shared catalog serves MK1/MK2 and slices.
    keys = sorted(set(previous) | source_keys(root))
    translations = {key: key for key in keys}
    digest = hashlib.sha256(json.dumps(translations, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode('utf-8')).hexdigest()
    base = dict(schema=1, catalog_version=VERSION, catalog_sha256=digest)
    english = dict(base, locale='en', name='English', translations=translations,
                   protected_keys=[k for k in keys if PROTECTED.search(k) or TECHNICAL.fullmatch(k)])
    template = dict(base, locale='xx', name='Your language', translations={})
    vendor = root / 'ui/languages/i18next.min.js'
    manifest = dict(base, app_version=tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version'],
                    base_language='en', available=['en'], engine='i18next', engine_version='26.5.5',
                    engine_sha256=hashlib.sha256(vendor.read_bytes()).hexdigest(),
                    key_count=len(keys), packs_url='https://github.com/Axelman8/ToneCommand/releases',
                    coverage='Initial shipped markup and marked FX3/controller messages; live plans and device/user text excluded.')
    return dict(zip(ASSETS, (english, template, manifest)))


def refresh(root=ROOT):
    folder = Path(root) / 'ui/languages'
    for name, value in documents(root).items():
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def check(root=ROOT):
    folder = Path(root) / 'ui/languages'
    for name, expected in documents(root).items():
        if json.loads((folder / name).read_text(encoding='utf-8')) != expected:
            raise ValueError('Language assets are stale; run python -m tools.language_packs --refresh: ' + name)
    print('English catalog, template and release manifest match the source.')


def build(root=ROOT, destination=None):
    root = Path(root)
    check(root)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    tracked = subprocess.check_output(['git', 'status', '--porcelain', '--',
        'ui/languages', 'docs/LANGUAGE-PACKS.md', 'tools/language_packs.py'], cwd=root)
    if tracked.strip():
        raise ValueError('Commit tested language assets before publishing an archive')
    folder = Path(destination or root / 'dist')
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / ('ToneCommand-Language-Packs-' + VERSION + '.zip')
    if output.exists():
        raise FileExistsError('Refusing to replace an existing language release ZIP')
    files = {name: (root / 'ui/languages' / name).read_bytes() for name in ASSETS}
    files['LANGUAGE-PACKS.md'] = (root / 'docs/LANGUAGE-PACKS.md').read_bytes()
    files['SOURCE.json'] = json.dumps(dict(source_commit=revision, version=VERSION,
        files={name: hashlib.sha256(data).hexdigest() for name, data in files.items()}), indent=2).encode()
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(checksum + '  ' + output.name + '\n', encoding='ascii')
    print(json.dumps(dict(path=str(output), source_commit=revision, sha256=checksum)))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--refresh', action='store_true')
    group.add_argument('--build', action='store_true')
    args = parser.parse_args()
    refresh() if args.refresh else build() if args.build else check()
