"""How strongly a result is known, in words that cannot be swapped.

Issue #58. The failure this prevents happened on hardware: three cab level
writes were reported as "verified by read-back". The read-back was accurate and
the writes did land. The parameter simply was not in the audio path, so nothing
changed audibly. The claim was true and the word was too strong, and the player
reasonably heard "verified" as "the sound was confirmed".

The ladder, weakest to strongest. Each rung means exactly one thing:

    sent              commands were transmitted
    read_back         the FM9 reported the intended state
    sound_checked     controlled output was captured at a named boundary
    closer_to_target  a stated measurable criterion moved correctly
    your_pick         the player preferred it in a controlled comparison
    kept              the player explicitly retained the version
    field_noted       the player reported an outcome in a named context

Two rules the rest of the codebase must respect:

1. A verified write is NOT evidence the parameter is in the audio path.
   read_back is the ceiling for anything the device merely echoed back.
2. `better` belongs to the player. The system never asserts it, and no rung
   above `closer_to_target` can be reached without the player saying so.
"""
from __future__ import annotations

#: Ordered weakest to strongest. Index is the strength.
LADDER = ["sent", "read_back", "sound_checked", "closer_to_target",
          "your_pick", "kept", "field_noted"]

#: What each rung means, and the copy a player sees. The copy deliberately
#: avoids "verified", which reads as a claim about sound.
CLAIMS = {
    "sent": ("commands were transmitted",
             "Sent"),
    "read_back": ("the FM9 reported the intended state",
                  "Read back on the unit"),
    "sound_checked": ("controlled output was captured at a named boundary",
                      "Sound checked"),
    "closer_to_target": ("a stated measurable criterion moved correctly",
                         "Closer to target"),
    "your_pick": ("the player preferred it in a controlled comparison",
                  "Your pick"),
    "kept": ("the player explicitly retained the version",
             "Kept"),
    "field_noted": ("the player reported an outcome in a named context",
                    "Field noted"),
}

#: Words the SYSTEM may never use about a result. They are judgements, and
#: judgement is the player's. Checked by tests against the UI and this module.
RESERVED_FOR_THE_PLAYER = ("better", "worse", "improved", "perfect", "great",
                           "amazing", "fixed the tone", "sounds right")

#: The strongest claim a device echo can support. Anything that only read the
#: value back stops here, however trustworthy the read was.
CEILING_FOR_DEVICE_ECHO = "read_back"


def strength(level: str) -> int:
    return LADDER.index(level) if level in LADDER else -1


def highest(*levels: str) -> str:
    """The strongest claim among those actually earned."""
    earned = [l for l in levels if l in LADDER]
    return max(earned, key=strength) if earned else "sent"


def copy_for(level: str) -> str:
    return CLAIMS.get(level, CLAIMS["sent"])[1]


def describe(sent: bool = False, read_back: bool = False,
             sound_checked: bool = False, moved_to_target: bool = False,
             player_picked: bool = False, player_kept: bool = False) -> dict:
    """The strongest claim these facts support, and nothing above it.

    Deliberately takes booleans for what actually happened rather than a
    free-text status, so a caller cannot smuggle a stronger word in.
    """
    level = "sent"
    if sent:
        level = "sent"
    if read_back:
        level = "read_back"
    if sound_checked:
        level = "sound_checked"
    if moved_to_target:
        if not sound_checked:
            # Nothing can be closer to a target without a measurement to say so.
            raise ValueError("moved_to_target requires sound_checked")
        level = "closer_to_target"
    if player_picked:
        level = "your_pick"
    if player_kept:
        level = "kept"
    return {
        "level": level,
        "label": copy_for(level),
        "means": CLAIMS[level][0],
        "audio_confirmed": strength(level) >= strength("sound_checked"),
        "caveat": ("A read-back proves the write landed. It does not prove the "
                   "parameter is in the audio path."
                   if level == "read_back" else ""),
    }


def overclaims(text: str) -> list[str]:
    """Any reserved judgement word appearing in system-authored copy."""
    low = (text or "").lower()
    return [w for w in RESERVED_FOR_THE_PLAYER if w in low]
