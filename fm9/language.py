"""Local, allowlisted language assets. No AI, network, settings or MIDI."""
import re

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fm9.paths import resource_path

ASSETS = {
    'i18next.min.js': 'text/javascript',
    'i18next.LICENSE': 'text/plain',
    'tc-language.js': 'text/javascript',
    'tc-language.css': 'text/css',
    'en.json': 'application/json',
    'template.json': 'application/json',
    'manifest.json': 'application/json',
}
for _path in resource_path('ui', 'languages').glob('*.json'):
    if re.fullmatch(r'[a-z]{2,3}(?:-[A-Z]{2})?\.json', _path.name):
        ASSETS[_path.name] = 'application/json'


def register(app):
    @app.get('/language/{asset}')
    def language_asset(asset: str):
        if asset not in ASSETS:
            raise HTTPException(404, 'Unknown language asset')
        return FileResponse(resource_path('ui', 'languages', asset),
                            media_type=ASSETS[asset],
                            headers={'Cache-Control': 'no-cache'})
