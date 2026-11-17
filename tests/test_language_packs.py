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


def test_existing_addon_marked_messages_are_in_english_catalog():
    catalog=json.loads((ROOT/'ui/languages/en.json').read_text(encoding='utf-8'))
    for message in ('READ ALL 8 SCENES','Adjust this existing preset',
                    'I confirm the current preset is the one to adjust.',
                    'Prepare a fresh proposal first.'):
        assert message in catalog['translations']


def test_scanner_collects_both_static_quote_styles_not_dynamic_data(tmp_path):
    script=tmp_path/'ui/axefx3-existing-edit.js';script.parent.mkdir()
    script.write_text('t("Double");t(\'Single\');t(row.reason);t(`live ${name}`);',encoding='utf-8')
    assert packs.source_keys(tmp_path)=={'Double','Single'}


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
    assert "jsonAsset('en.json')" in code
    assert 'new Function' not in code and 'eval(' not in code
    assert 'showModal' not in code and 'type="file"' not in code
    assert 'Axelman8' not in code


def test_settings_has_one_native_language_choice_and_no_import_dialog():
    page = (ROOT / 'ui/index.html').read_text(encoding='utf-8')
    settings = page.split('id="drawer-settings"', 1)[1]
    assert settings.count('id="tc-language-select"') == 1
    assert page.count('id="tc-language-select"') == 1
    assert 'tc-language-dialog' not in page
    assert not (ROOT / '.github/workflows/language-packs.yml').exists()


def test_bundled_dutch_and_german_are_data_only_and_match_the_catalog():
    english = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'ui/languages/manifest.json').read_text(encoding='utf-8'))
    assert manifest['available'] == ['en', 'de', 'nl']
    assert manifest['languages'] == [dict(locale='en', name='English'),
                                    dict(locale='de', name='Deutsch'), dict(locale='nl', name='Nederlands')]
    assert 'packs_url' not in manifest
    for locale in ('nl', 'de'):
        assert locale + '.json' in ASSETS
        pack = json.loads((ROOT / ('ui/languages/' + locale + '.json')).read_text(encoding='utf-8'))
        packs.validate_translations(pack, english, locale)
        assert pack['catalog_sha256'] == english['catalog_sha256']
        assert len(pack['translations']) >= 150
        assert pack['translations']['SETTINGS'] != 'SETTINGS'


@pytest.mark.parametrize('translations', [
    {'not-a-key': 'bad'}, {'{{v0}} ms (shared A)': 'bad'}, {'Language': '$t(unsafe)'},
    {'Language': ''}, {'Language': 1}, {'Language': ' '},
])
def test_invalid_bundled_entries_are_refused(translations):
    english = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError, match='translation'):
        packs.validate_translations(dict(schema=1, locale='nl', name='Nederlands',
                                         translations=translations), english, 'nl')


def test_protected_confirmation_cannot_be_translated():
    english = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError, match='translation'):
        packs.validate_translations(dict(schema=1, locale='nl', name='Nederlands',
            translations={english['protected_keys'][0]: 'Translated confirmation'}), english, 'nl')


def test_new_bundled_locale_needs_only_a_file_and_refreshed_metadata(tmp_path):
    (tmp_path / 'ui').mkdir()
    shutil.copytree(ROOT / 'ui/languages', tmp_path / 'ui/languages')
    shutil.copyfile(ROOT / 'pyproject.toml', tmp_path / 'pyproject.toml')
    (tmp_path / 'ui/languages/fr.json').write_text(json.dumps(dict(schema=1, locale='fr',
        name='Français', translations={'Language': 'Langue'})), encoding='utf-8')
    with pytest.raises(ValueError, match='stale'):
        packs.check(tmp_path)
    packs.refresh(tmp_path)
    packs.check(tmp_path)
    manifest = json.loads((tmp_path / 'ui/languages/manifest.json').read_text(encoding='utf-8'))
    assert dict(locale='fr', name='Français') in manifest['languages']


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
