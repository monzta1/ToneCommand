# Interface languages

Choose a language in **Settings > Language**. English, Nederlands and Deutsch
are bundled with ToneCommand. The choice applies immediately and is remembered
in this browser profile. There is no separate dialog, import step or download.
If browser storage is unavailable, the choice lasts for the current session.

The experimental FX3/controller workspaces expose the same native dropdown
inside SETTINGS. There is no additional language dialog or import control.
The same bundled loader and catalogs serve all three surfaces.

Dutch and German currently cover core request, navigation and Settings labels.
Other text falls back to English. Coverage is initial shipped markup and
explicitly marked messages; unmarked dynamic messages remain English.
Critical confirmations, protocol identifiers and technical names stay English.
User input, AI replies, existing plans and device/preset/model/cab names are
not translated. Native file pickers follow the browser and operating system.

The bundled i18next engine runs locally. Language selection contacts only the
local app for its shipped JSON files, not an AI, CDN, account or MIDI device.
It does not reload the page, submit input, change a plan or alter consent.
Only the locale choice is stored; previously imported translation data is not
loaded by this version. A missing, damaged or incompatible pack cannot enable
hardware features and falls back to English.

## Contribute a language

1. Copy `ui/languages/template.json` to a locale-named file such as `fr.json`.
   Use a two/three-letter locale, optionally followed by a region (`pt-BR`).
2. Set `locale` to that filename without `.json` and `name` to its native name.
3. Copy keys from `en.json` into `translations` and translate the values.
   Keep English keys and every `{{placeholder}}` unchanged. Partial translations
   are welcome: missing entries fall back to English.
4. Omit `protected_keys`, or retain those entries exactly in English. Never add
   executable code, HTML assumptions, presets, credentials or hardware captures.
5. Run `python -m tools.language_packs --refresh`, inspect the catalog/manifest
   changes, then run `python -m tools.language_packs` and the tests below.
6. Submit the language file and generated metadata in a PR to this repository,
   with a short coverage note. No server or dropdown code change is necessary.

The checker discovers locale files and puts them in the Settings list. It
rejects unknown keys, changed placeholders, translated protected text and
invalid metadata. All displayed translation values are text, not HTML.

## Maintenance and tests

After changing fixed UI text, refresh and review the catalog. Older public keys
are retained. Refresh updates bundled pack metadata to the current catalog;
new untranslated entries continue to fall back to English. Review translations
when source wording changes rather than assuming the old wording is equivalent.

```text
python -m tools.language_packs --refresh
python -m tools.language_packs
pytest tests/test_language_packs.py tests/test_ui_syntax.py tests/test_text_encoding.py -q
node tests/language_packs.browser.cjs
```

The browser test needs Playwright and Chromium/Chrome. `TC_PLAYWRIGHT_MODULE`
and `TC_BROWSER_EXECUTABLE` can select existing local installations. It mocks
all network requests and does not connect a device or use an AI account.

Language files ship with the normal app release. The manifest records catalog
version/hash, available native language names and the local engine checksum.
Upstream ships these files with the normal application. This fork retains its
optional local archive builder for historical package users, but no separate
publishing workflow or extra in-app download control.
After committing and testing a changed catalog, `python -m tools.language_packs
--build` creates a new archive/checksum; never overwrite an older release asset.
Language support is independent of firmware, device write permissions and MK1
acceptance. `tests/language_picker.browser.cjs` also covers the native workspace controls.
