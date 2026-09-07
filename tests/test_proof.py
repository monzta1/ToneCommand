"""Issue #58: sent, read back, sound checked and better are not synonyms."""
from __future__ import annotations

from pathlib import Path

import pytest

from fm9 import proof

ROOT = Path(__file__).resolve().parent.parent


def test_the_ladder_is_ordered_weakest_first():
    assert proof.strength("sent") < proof.strength("read_back")
    assert proof.strength("read_back") < proof.strength("sound_checked")
    assert proof.strength("sound_checked") < proof.strength("closer_to_target")
    assert proof.strength("closer_to_target") < proof.strength("your_pick")


def test_a_read_back_is_not_audio_confirmation():
    """The exact hardware failure: three level writes read back correctly and
    changed nothing audible, because the parameter was not in the audio path."""
    d = proof.describe(sent=True, read_back=True)
    assert d["level"] == "read_back"
    assert d["audio_confirmed"] is False
    assert "does not prove the parameter is in the audio path" in d["caveat"]


def test_read_back_copy_avoids_the_word_verified():
    assert "verif" not in proof.copy_for("read_back").lower()


def test_nothing_is_closer_to_target_without_a_measurement():
    with pytest.raises(ValueError, match="requires sound_checked"):
        proof.describe(sent=True, read_back=True, moved_to_target=True)


def test_measurement_alone_never_becomes_the_players_preference():
    d = proof.describe(sent=True, read_back=True, sound_checked=True,
                       moved_to_target=True)
    assert d["level"] == "closer_to_target"
    assert proof.strength(d["level"]) < proof.strength("your_pick")


def test_the_player_can_raise_it_and_only_the_player():
    assert proof.describe(sent=True, read_back=True,
                          player_picked=True)["level"] == "your_pick"
    assert proof.describe(sent=True, read_back=True, player_picked=True,
                          player_kept=True)["level"] == "kept"


def test_highest_picks_the_strongest_earned_claim():
    assert proof.highest("sent", "read_back") == "read_back"
    assert proof.highest() == "sent"


def test_every_rung_has_a_distinct_label():
    labels = [proof.copy_for(l) for l in proof.LADDER]
    assert len(set(labels)) == len(labels), "two rungs must never read alike"


# --- the system may not judge -------------------------------------------

def test_reserved_words_are_detected():
    assert "better" in proof.overclaims("this sounds better now")
    assert proof.overclaims("read back on the unit") == []


def test_no_claim_label_judges_the_result():
    for level in proof.LADDER:
        assert not proof.overclaims(proof.copy_for(level)), level


# --- the codebase must not overclaim ------------------------------------

def test_the_device_layer_no_longer_says_verified_by_read_back():
    """It said 'verified by read-back', which players read as confirmation of
    sound rather than of a write."""
    src = (ROOT / "fm9" / "device.py").read_text()
    assert "verified by read-back" not in src
    assert "read back on the unit" in src
