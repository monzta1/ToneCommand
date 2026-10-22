# Interface language packs

English is ToneCommand's base interface language. Optional JSON packs translate
registered labels without changing preset data, protocol identifiers or device
permissions. The translation engine, i18next 26.5.5, ships locally. No AI,
translation account, CDN or external translation request is used.

## Choose or import a language

Open Settings, then LANGUAGE. On the FX3/controller/tester page the LANGUAGE
button is in the header. English is always available. Download a matching pack
from [the fork's releases](https://github.com/Axelman8/ToneCommand/releases),
then import the extracted JSON file. Import only reviewed files from a trusted
source. A ZIP is a download container, not an executable installer.

The choice is kept in this browser profile. If browser storage is disabled it
is session-only. Changing language makes no network request to an AI or device,
does not reload the page and does not discard input, plans or consent. It also
does not grant permission for a hardware operation. Untranslated text remains
English; no browser-language autodetection silently changes the app.

This first release supplies English and a translator template, not a completed
Dutch, German or other translation. Coverage is initial shipped markup and
marked FX3/controller messages. Unmarked dynamic FM9 messages remain English.
Existing plans, AI replies, user input, preset/cab/model names and raw technical
details are not machine translated. Native file pickers follow the browser/OS.

## Create a translation

1. Copy `template.json` and set `locale` (for example `nl`) and `name`.
2. Copy entries from `en.json` into `translations` and translate their values.
   Keep each English key unchanged. Keep `{{placeholders}}` unchanged.
3. Keep `schema`, `catalog_version` and `catalog_sha256` exactly as downloaded.
4. Do not change entries listed in `protected_keys`. Critical confirmations and
   exact technical identifiers remain English in this first release. Translating
   those requires a separately reviewed application/catalog update.
5. Test import, fallback and layout without connecting a device. Submit only
   the JSON and a short coverage note, never presets, accounts, recordings or
   hardware captures. Translations are text, never HTML or JavaScript.

Partial packs are allowed. Unknown keys, incompatible catalogs, changed
placeholders and files larger than 2 MiB are refused. New model/parameter names
must not be added as translation keys merely to change what TC sends.

## Release maintenance

Run `python -m tools.language_packs --refresh` after changing source UI text,
review the diff, and run `python -m tools.language_packs` plus language and
browser tests before committing. Older public keys are retained. The manifest
records the app version, catalog version/hash, key count and local engine hash.

After committing the tested assets, run
`python -m tools.language_packs --build`. Upload the new ZIP, checksum and JSON
assets to a new GitHub pre-release. Do not overwrite older downloads or move
their tags. Language packages are versioned separately from Fractal firmware.
The release gate fails if the source, catalog, template or manifest disagree.

The fork-only `language-packs.yml` workflow performs that check and attaches
the tagged catalog when a release is published. It also supports an existing
release tag through workflow dispatch. It never overwrites assets. GitHub
requires the workflow to be available on the repository's default branch;
until that change is merged, use the tested local build/upload procedure.
Increase `VERSION` in the builder for a changed catalog release, refresh the
catalog, and update translations against that exact version and hash.

A changed catalog needs an updated pack with the new hash; stale imports fall
back to English rather than silently approving changed safety instructions.
MK1 and MK2 can share the same catalog, but language support never unlocks
MK1 writes or NAM installation. Hardware acceptance remains separate.
