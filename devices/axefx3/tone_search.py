"""Authenticated TONE3000 A2/IR discovery. No installs or hardware writes."""
import json
from urllib.parse import urlencode

from fm9 import recipe_capture, tone3000_auth


def search(query, format='nam', *, http=None, key=None):
    query = query.strip()
    if not query or len(query) > 250 or format not in ('nam', 'ir'):
        raise ValueError('Use a search term of 1-250 characters and NAM or IR.')
    key = key or recipe_capture.key_from_env()
    if not key:
        raise ValueError('Sign in to TONE3000 in TC settings before searching.')
    params = dict(query=query, page=1, page_size=8, sort='best-match', format=format)
    if format == 'nam':
        params['architecture'] = '2'
    status, body = (http or tone3000_auth.default_http)(
        'GET', tone3000_auth.HOST + '/api/v1/tones/search?' + urlencode(params),
        None, {'Authorization': 'Bearer ' + key})
    if status != 200:
        raise ValueError('TONE3000 search refused (HTTP %s). Retry later or sign in again.' % status)
    try:
        rows = json.loads(body)['data']
    except (ValueError, KeyError, TypeError):
        raise ValueError('TONE3000 returned an invalid search result.') from None
    if not isinstance(rows, list):
        raise ValueError('TONE3000 returned an invalid search result.')
    candidates = []
    for row in rows[:8]:
        if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] <= 0:
            continue
        user = row.get('user') if isinstance(row.get('user'), dict) else {}
        candidates.append(dict(id=row['id'], title=str(row.get('title', ''))[:180],
                               format=format, architecture='2' if format == 'nam' else None,
                               url=tone3000_auth.HOST + '/tones/' + str(row['id']),
                               creator=str(user.get('username', ''))[:100],
                               license=row.get('license'),
                               note='Search match, not a proven recording match or an installed block.'))
    return dict(query=query, candidates=candidates, hardware_written=False, nam_install_supported=False)
