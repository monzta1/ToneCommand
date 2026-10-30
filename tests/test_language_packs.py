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


def test_pitch_buttons_and_expiry_are_in_bundled_catalogs():
    keys=('Send Pitch setup','Pitch setup read back and confirmed',
          'This review expires after {{seconds}} seconds or when device state changes.')
    for locale in ('en','nl','de'):
        pack=json.loads((ROOT/f'ui/languages/{locale}.json').read_text(encoding='utf-8'))
        assert all(key in pack['translations'] for key in keys)
        assert '{{seconds}}' in pack['translations'][keys[2]]


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


def test_bundled_languages_are_valid_and_discovered():
    catalog = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'ui/languages/manifest.json').read_text(encoding='utf-8'))
    assert set(manifest['available']) == {'en', 'nl', 'de'}
    for locale in ('nl', 'de'):
        pack = json.loads((ROOT / f'ui/languages/{locale}.json').read_text(encoding='utf-8'))
        packs.validate_translations(pack, catalog, locale)
        assert pack['catalog_sha256'] == catalog['catalog_sha256']
        assert len(pack['translations']) >= 150
        assert f'{locale}.json' in ASSETS


@pytest.mark.parametrize('translation', [{'not-a-key': 'wrong'}, {'Language': '$t(secret)'}])
def test_invalid_bundled_translation_fails_closed(translation):
    catalog = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError, match='translation'):
        packs.validate_translations(dict(schema=1, locale='nl', name='Nederlands',
                                         translations=translation), catalog, 'nl')


def test_protected_confirmation_cannot_be_translated():
    catalog = json.loads((ROOT / 'ui/languages/en.json').read_text(encoding='utf-8'))
    with pytest.raises(ValueError, match='translation'):
        packs.validate_translations(dict(schema=1, locale='nl', name='Nederlands',
            translations={catalog['protected_keys'][0]: 'Changed confirmation'}), catalog, 'nl')


def test_new_locale_is_in_manifest_and_release_documents(tmp_path):
    (tmp_path / 'ui').mkdir()
    shutil.copytree(ROOT / 'ui/languages', tmp_path / 'ui/languages')
    shutil.copyfile(ROOT / 'pyproject.toml', tmp_path / 'pyproject.toml')
    (tmp_path / 'ui/languages/fr.json').write_text(json.dumps(dict(schema=1, locale='fr',
        name='French', translations={'Language': 'Langue'})), encoding='utf-8')
    with pytest.raises(ValueError, match='stale'):
        packs.check(tmp_path)
    packs.refresh(tmp_path)
    packs.check(tmp_path)
    assert 'fr.json' in packs.documents(tmp_path)


def test_workspace_language_choices_use_the_shared_native_dropdown():
    code = (ROOT / 'ui/languages/tc-language.js').read_text(encoding='utf-8')
    assert 'showModal' not in code and 'tc-language-dialog' not in code
    assert 'type="file"' not in code and 'GitHub language packs' not in code
    for name in ('axefx3.html', 'controllers.html'):
        page = (ROOT / 'ui' / name).read_text(encoding='utf-8')
        assert page.count('id="tc-language-select"') == 1
        assert '<label for="tc-language-select">Language</label>' in page
        assert 'id="workspaceSettings"' in page and '<summary>SETTINGS</summary>' in page
        assert 'id="tc-language-status" role="status"' in page


def test_tone3000_fixed_status_uses_english_source_and_bundled_translations():
    script = (ROOT / 'ui/axefx3.js').read_text(encoding='utf-8')
    page = (ROOT / 'ui/axefx3.html').read_text(encoding='utf-8')
    assert 'Account verbonden.' not in script
    assert 'Geen access token of wachtwoord' not in page
    assert 'tcText("Account connected.")' in script
    assert "addEventListener('tc-language-changed',renderAccountStatus)" in script
    assert 'placeholder="Not an access token or password"' in page
    for locale, status, placeholder in (
        ('en', 'Account connected.', 'Not an access token or password'),
        ('nl', 'Account verbonden.', 'Geen access token of wachtwoord'),
        ('de', 'Konto verbunden.', 'Kein Access-Token oder Passwort'),
    ):
        pack = json.loads((ROOT / f'ui/languages/{locale}.json').read_text(encoding='utf-8'))
        assert pack['translations']['Account connected.'] == status
        assert pack['translations']['Not an access token or password'] == placeholder
