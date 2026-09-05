"""Relative per-scene loudness in plain language: "turn everything except scene
1 down 5 dB". The point of the feature is that the tool reads the current level
and applies the delta itself; the planner cannot read the values, so a request
like this must never bounce back asking the player for a number.

These cover the parse (server.parse_level_adjust): it finds the right amount even
when a "scene N" number is also in the sentence, reads the direction, resolves
the scope (all / all-but-N / just scene N), and stays out of requests that are
not level changes.
"""
import sys

sys.argv = ["x"]
import server


def test_everything_except_a_scene_reads_amount_not_the_scene_number():
    p = server.parse_level_adjust("turn everything except scene 1 down 5db")
    assert p == {"delta": -5.0, "scenes": [2, 3, 4, 5, 6, 7, 8]}


def test_everything_down():
    p = server.parse_level_adjust("turn everything down 5 db")
    assert p["delta"] == -5.0 and p["scenes"] == [1, 2, 3, 4, 5, 6, 7, 8]


def test_a_single_scene_up_without_db():
    p = server.parse_level_adjust("scene 3 up 2")
    assert p == {"delta": 2.0, "scenes": [3]}


def test_all_but_a_scene_quieter_by():
    p = server.parse_level_adjust("all but scene 1 quieter by 4")
    assert p == {"delta": -4.0, "scenes": [2, 3, 4, 5, 6, 7, 8]}


def test_direction_words_map_to_sign():
    assert server.parse_level_adjust("make scene 7 louder by 3 db")["delta"] == 3.0
    assert server.parse_level_adjust("scene 7 quieter by 3 db")["delta"] == -3.0


def test_not_a_level_change_is_ignored():
    for t in ["make it warmer", "add more gain", "move the delay up",
              "give me an 80s tone", "louder and quieter"]:
        assert server.parse_level_adjust(t) is None, t


def test_no_amount_is_ignored():
    assert server.parse_level_adjust("turn everything down") is None
