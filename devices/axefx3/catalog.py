"""Local cabinet-name imports. These are catalogues, NEVER IR installs."""
import csv
import io
import re
from .chassis import modern_cab_metadata


def parse_names(text: str, kind: str, *, firmware='32.06') -> dict[tuple[int, int], str]:
    if kind not in {"user", "factory"}:
        raise ValueError("List type must be User or Factory.")
    prefix = "U" if kind == "user" else "F"
    modern = modern_cab_metadata(firmware)
    entries = {}
    for raw in text.splitlines():
        line = raw.strip().lstrip('\ufeff')
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r"([UF])([1-9])\.(\d{1,4})\s+(.+)", line, re.I)
        if match:
            p, bank, slot, name = match.groups()
            if p.upper() != prefix:
                raise ValueError(f"This is not a {kind} list: {line[:40]}")
        elif ',' in line or ';' in line or '\t' in line:
            delimiter = '\t' if '\t' in line else ';' if ';' in line else ','
            row = next(csv.reader(io.StringIO(line), delimiter=delimiter))
            if row and row[0].strip().lower() == 'bank':
                continue
            if len(row) != 3:
                raise ValueError("CSV columns must be bank,slot,name.")
            bank, slot, name = (x.strip() for x in row)
            bank_type = re.match(r'^(USER|FACTORY|[UF])', bank, re.I)
            if bank_type and bank_type[1].upper()[0] != prefix:
                raise ValueError(f'This is not a {kind} list: {bank}')
            bank = re.sub(r'^(?:USER|FACTORY|[UF])\s*', '', bank, flags=re.I)
        else:
            if re.match(r'[UF]\d', line, re.I):
                raise ValueError(f"Invalid cabinet entry: {line[:60]}")
            continue  # Export headings are not entries.
        try:
            bank, slot = int(bank), int(slot)
        except ValueError:
            raise ValueError("Bank and slot must be whole numbers.") from None
        banks = (1, 2, 3) if kind == 'user' and modern else (1, 2)
        limit = 64 if kind == 'user' and modern and bank == 3 else 1024 if modern or kind == 'factory' else 512
        if bank not in banks or not 1 <= slot <= limit:
            raise ValueError(f"{kind.title()} bank {bank}, slot {slot} is not an Axe-Fx III name-list address. "
                             f"Supported banks: {banks}; slots in this bank: 1-{limit}. "
                             "No entries imported or silently renumbered.")
        name = re.sub(r'\s+\(\*\)\s*$', '', name).strip()
        if not name or len(name) > 160 or any(ord(c) < 32 for c in name):
            raise ValueError("Cabinet names must contain 1–160 printable characters.")
        key = (bank, slot)
        if key in entries and entries[key] != name:
            raise ValueError(f"Conflicting names for {prefix}{bank}.{slot:04d}.")
        entries[key] = name
    if not entries:
        raise ValueError(f"No {prefix}1.0001-style entries or bank,slot,name CSV found.")
    return entries


def wire_address(kind, bank, slot, *, firmware='32.06'):
    """Convert explicit display bank/slot, never infer the other device's bank."""
    if kind not in {"factory", "user"} or type(bank) is not int or type(slot) is not int:
        raise ValueError("Explicit list kind and integer bank/slot required")
    modern = modern_cab_metadata(firmware)
    banks = (1, 2, 3) if modern and kind == 'user' else (1, 2)
    limit = 64 if modern and kind == 'user' and bank == 3 else 1024 if modern or kind == 'factory' else 512
    if bank not in banks or slot not in range(1, limit + 1):
        raise ValueError("Cab bank/slot outside the verified range")
    if modern and kind == 'user':
        return ({1:2, 2:3, 3:6}[bank], slot-1)
    return (2, (bank - 1) * 512 + slot - 1) if kind == "user" else (bank - 1, slot - 1)


class Catalog:
    """Names are local user-supplied metadata, never evidence an IR is audible."""

    def __init__(self, firmware='32.06'):
        self.firmware = firmware
        self.names = {}
        self.user2_enabled = True
        self.fullres_enabled = True

    def import_text(self, text, kind, *, replace=False):
        if not isinstance(text, str) or len(text.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Cab name list exceeds 2 MiB or is not text")
        parsed = parse_names(text, kind, firmware=self.firmware)
        if kind == 'user' and not self.user2_enabled and any(b == 2 for b, s in parsed):
            raise ValueError('User2 is reserved for NAM on MK1/unknown NAM-era hardware. Import User1 only, or confirm MK2.')
        if kind == 'user' and not self.fullres_enabled and any(b == 3 for b, s in parsed):
            raise ValueError('Persistent FullRes User3 requires MK2 storage; MK1 Scratchpad is not this bank.')
        incoming = {wire_address(kind, b, s, firmware=self.firmware): n for (b, s), n in parsed.items()}
        user_banks = (2, 3, 6) if modern_cab_metadata(self.firmware) else (2,)
        merged = {key: name for key, name in self.names.items()
                  if not replace or (key[0] in user_banks) != (kind == "user")}
        merged.update(incoming)
        self.names = merged
        return len(incoming)

    def resolve(self, name, bank=None):
        matches = [(b, o, n) for (b, o), n in self.names.items()
                   if n.casefold() == name.strip().casefold() and (bank is None or b == bank)]
        if len(matches) != 1:
            raise ValueError("Cab name is unknown or ambiguous; choose an explicit bank and slot")
        return matches[0]

    def position(self, bank, ordinal):
        if modern_cab_metadata(self.firmware):
            limits = {0:1024, 1:1024, 2:1024, 3:1024, 6:64}
            if type(bank) is not int or type(ordinal) is not int or bank not in limits or not 0 <= ordinal < limits[bank]:
                raise ValueError('Unknown Axe-Fx III IR address')
            label = {0:'FACTORY 1', 1:'FACTORY 2', 2:'USER 1', 3:'USER 2', 6:'USER 3 (FullRes)'}[bank]
            return f'{label} slot {ordinal+1}'
        if type(bank) is not int or type(ordinal) is not int or bank not in (0, 1, 2) or ordinal not in range(1024):
            raise ValueError("Unknown Axe-Fx III IR address")
        return (f"USER {ordinal // 512 + 1} slot {ordinal % 512 + 1}"
                if bank == 2 else f"FACTORY {bank + 1} slot {ordinal + 1}")

    def rosters(self):
        banks = (0, 1, 2, 3, 6) if modern_cab_metadata(self.firmware) else (0, 1, 2)
        return {str(b): {str(o): n for (bank, o), n in self.names.items() if bank == b} for b in banks}

    def restrict_user2(self, enabled):
        """Apply whole-bank NAM protection, never half of a FW33 User1 bank."""
        self.user2_enabled = enabled
        if not enabled:
            self.names = {k:v for k,v in self.names.items()
                          if not (k[0] == 3 if modern_cab_metadata(self.firmware) else k[0] == 2 and k[1] >= 512)}

    def restrict_fullres(self, enabled):
        """Persistent User3 names are not the MK1's temporary Scratchpad."""
        self.fullres_enabled = enabled
        if not enabled:
            self.names = {k: v for k, v in self.names.items() if k[0] != 6}
