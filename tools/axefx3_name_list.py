"""Offline comparison of an Axe-Edit text name export and TC's name list.

No MIDI, AI, preset selection or write permissions. Names remain local data.
"""
import argparse
import json
from pathlib import Path
import re

COUNTS = {'mk1': 512, 'mk2': 1024, 'turbo': 1024}
MAX_BYTES = 1024 * 1024


def _count(chassis):
    if type(chassis) is not str or chassis not in COUNTS:
        raise ValueError('Declare mk1, mk2 or turbo; this does not detect hardware')
    return COUNTS[chassis]


def editor_names(text, chassis):
    """Parse the observed four-digit/two-space/tab format without stripping names."""
    count = _count(chassis)
    if type(text) is not str or len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Editor name export is not bounded text')
    rows = {}
    for line in text.removeprefix('\ufeff').splitlines():
        match = re.fullmatch(r'([0-9]{4})  \t([^\t\r\n]{0,31})', line)
        if not match:
            raise ValueError('Unexpected Axe-Edit name export format; no whitespace guessing')
        number = int(match[1])
        if number not in range(count) or number in rows:
            raise ValueError('Duplicate or out-of-range editor slot')
        rows[number] = match[2]
    if set(rows) != set(range(count)):
        raise ValueError('Editor name list is incomplete for the declared chassis')
    return rows


def native_names(data, chassis):
    count = _count(chassis)
    slots = data.get('slots') if type(data) is dict else data
    if type(slots) is not list or len(slots) != count:
        raise ValueError('TC name list is incomplete for the declared chassis')
    rows = {}
    for slot in slots:
        if (type(slot) is not dict or type(slot.get('number')) is not int
                or slot['number'] not in range(count) or slot['number'] in rows
                or type(slot.get('name')) is not str or len(slot['name']) > 31
                or any(c in slot['name'] for c in '\t\r\n')):
            raise ValueError('Invalid or duplicate TC name entry')
        rows[slot['number']] = slot['name']
    return rows


def compare(text, data, chassis):
    expected, actual = editor_names(text, chassis), native_names(data, chassis)
    different = [n for n in expected if expected[n] != actual[n]]
    spaces = [n for n in different if expected[n].strip(' ') == actual[n].strip(' ')]
    return dict(equal=not different, chassis=chassis, count=len(expected),
                matched=len(expected)-len(different), mismatch_slots=different,
                outer_space_only_slots=spaces,
                upper_matched=sum(expected[n] == actual[n] for n in expected if n >= 512),
                midi_opened=False, write_permissions_changed=False)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key in TC name export')
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--editor-export', required=True, type=Path)
    parser.add_argument('--tc-export', required=True, type=Path)
    parser.add_argument('--chassis', required=True, choices=tuple(COUNTS))
    args = parser.parse_args(argv)
    for path in (args.editor_export, args.tc_export):
        if path.stat().st_size > MAX_BYTES:
            raise ValueError('Name-list file is too large')
    result = compare(args.editor_export.read_text(encoding='utf-8-sig'),
                     json.loads(args.tc_export.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique),
                     args.chassis)
    # Counts and indices only. Do not publish the player's preset names.
    print(json.dumps(result))
    return 0 if result['equal'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
