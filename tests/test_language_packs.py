import hashlib
import json
from pathlib import Path
import shutil

from fastapi.testclient import TestClient
import pytest
import server
from fm9.language import ASSETS
from tools import language_packs as packs

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_and_manifest_are_current():
    packs.check(ROOT)
    catalog = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    assert catalog['locale'] == 'en' and catalog['schema'] == 1
    assert len(catalog['translations']) >= 200
    assert all(key == value for key, value in catalog['translations'].items())
    assert 'Interface language' in catalog['translations']
    assert catalog['protected_keys']


@pytest.mark.parametrize('asset', list(ASSETS))
def test_assets_are_local_reads_that_never_get_a_device(monkeypatch, asset):
    monkeypatch.setattr(server, 'get_fm9', lambda: pytest.fail('language asset reached MIDI'))
    with TestClient(server.app) as client:
        response = client.get('/language/' + asset)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-cache'
    assert response.content


@pytest.mark.parametrize('asset', ['ai_settings.json', 'server.py', 'other.js', 'user_cabs.json'])
def test_unknown_asset_cannot_read_private_files(asset):
    with TestClient(server.app) as client:
        assert client.get('/language/' + asset).status_code == 404


def test_no_post_installs_or_downloaded_code():
    with TestClient(server.app) as client:
        assert client.post('/language/en.json', json={}).status_code == 405
    code = (ROOT / 'ui/languages/tc-language.js').read_text(encoding='utf-8')
    assert 'MutationObserver' not in code
    assert 'innerHTML = translations' not in code
    assert "fetch('/language/en.json')" in code
    assert 'new Function' not in code and 'eval(' not in code


def test_vendor_hash_and_license():
    manifest = json.loads((ROOT / 'ui/languages/manifest.json').read_text(encoding='utf-8'))
    assert manifest['engine_version'] == '26.5.5'
    assert hashlib.sha256((ROOT / 'ui/languages/i18next.min.js').read_bytes()).hexdigest() == manifest['engine_sha256']
    assert 'Permission is hereby granted' in (ROOT / 'ui/languages/i18next.LICENSE').read_text(encoding='utf-8')


def test_release_check_catches_changed_source_and_stale_manifest(tmp_path):
    (tmp_path / 'ui').mkdir()
    shutil.copytree(ROOT / 'ui/languages', tmp_path / 'ui/languages')
    shutil.copyfile(ROOT / 'pyproject.toml', tmp_path / 'pyproject.toml')
    (tmp_path / 'ui/index.html').write_text('<button>New release label</button>', encoding='utf-8')
    with pytest.raises(ValueError, match='stale'):
        packs.check(tmp_path)
    packs.refresh(tmp_path)
    packs.check(tmp_path)
    catalog = json.loads((tmp_path / 'ui/languages/en.json').read_text(encoding='utf-8'))
    assert 'New release label' in catalog['translations']


def test_markup_does_not_collect_scripts_or_user_input():
    markup = packs.Markup()
    markup.feed('<label>Name<input placeholder="Your name"></label>'
                '<textarea>User text</textarea><script>secret()</script><style>style</style>')
    assert markup.keys == {'Name', 'Your name'}
