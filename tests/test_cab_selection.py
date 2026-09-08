"""Cabinet selection is a plannable action now (issue #45).

The executor already had a verified set_cab (discrete write + integer read-back);
the gap was that the planner could not emit it and was told cabs were not
plannable. These pin the wiring: a curated factory roster the planner can pick
from, set_cab in the planner's vocabulary, and the old gate gone.
"""
import sys

sys.argv = ["x"]
import server
from fm9 import planner
from server import Action, validate_action


def test_set_cab_is_in_the_planner_vocabulary():
    assert "set_cab" in planner.ACTION_KINDS


def test_the_planner_schema_carries_a_bank_field_for_set_cab():
    props = planner.PLAN_SCHEMA["properties"]["actions"]["items"]["properties"]
    assert "bank" in props
    req = planner.PLAN_SCHEMA["properties"]["actions"]["items"]["required"]
    assert "bank" in req, "every action must carry bank (nullable) under the schema"


def test_the_curated_roster_is_real_and_verifiable():
    cabs = server.curated_cab_roster()
    assert len(cabs) > 30, "expected a usable roster of workhorse cabs"
    # every ordinal is a real entry in the bank, so set_cab verifies by read-back
    for bank, ordn, name in cabs:
        assert str(ordn) in server.reg.cab_rosters[str(bank)]
        assert name and "(" not in name.split()[0]  # mic suffix stripped
    # it includes recognisable workhorses
    joined = " ".join(n for _, _, n in cabs).upper()
    assert "V30" in joined and "TWEED" in joined and "RECTO" in joined


def test_a_set_cab_from_the_roster_validates():
    bank, ordn, _ = server.curated_cab_roster()[0]
    errs, _ = validate_action(Action(kind="set_cab", block="cab",
                                     bank=bank, value=ordn))
    assert errs == []


def test_a_cab_ordinal_not_in_the_bank_is_refused():
    errs, _ = validate_action(Action(kind="set_cab", block="cab",
                                     bank=3, value=99999))
    assert errs and "not in bank" in errs[0]


def test_the_reference_no_longer_says_cabs_are_not_plannable():
    pr = server.param_reference()
    assert "NOT a plannable" not in pr
    assert "selectable via set_cab" in pr


# --- the cab has to have a NAME (2026-09-07) ----------------------------
#
# Reported on a Steve Vai build: no question was asked about the cab and
# nothing was said about how one was chosen. One cause was that the review
# renders `cab_name` when it has one and otherwise falls back to
# "bank 3 - ordinal 42", and the server never populated it.

def test_a_planned_cab_arrives_with_a_name(monkeypatch):
    """Resolved server side for the same reason as the store slot label: the
    roster lives here, so the browser should not be looking numbers up."""
    from fastapi.testclient import TestClient
    import server
    from fm9.sim import SimFM9
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    client = TestClient(server.app)
    monkeypatch.setattr(server.planner, "plan", lambda *a, **kw: {
        "summary": "voice it", "clarification": None,
        "actions": [{"kind": "set_cab", "block": "CABINET", "instance": 1,
                     "bank": 3, "value": 42, "reason": "matches the amp"}]})
    plan = client.post("/api/plan", json={"prompt": "give me a recto cab"}).json()
    a = plan["actions"][0]
    assert a.get("cab_name"), "the review would show a bare ordinal"
    assert "4x12" in a["cab_name"] or "RECTO" in a["cab_name"].upper()


def test_a_user_cab_is_named_from_the_players_own_labels(monkeypatch):
    """No catalogue can list the player's own IRs, which is what
    user_cabs.json exists for."""
    import server
    from fm9 import user_cabs
    monkeypatch.setattr(user_cabs, "name",
                        lambda b, o: "Soldano SLO30 - Emil Rohbe"
                        if (str(b), str(o)) == ("2", "26") else None)
    assert "Soldano SLO30" in server.cab_label(2, 26)


def test_an_unknown_ordinal_is_not_given_an_invented_name():
    import server
    got = server.cab_label(2, 99999)
    assert "99999" in got and "cab" in got.lower()


def test_the_review_prefers_the_name_over_the_numbers():
    """Pins the UI side of the same contract."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    assert "a.cab_name || a.label" in ui


def test_a_build_that_changes_the_amp_never_goes_quiet_about_the_cab():
    """A plan that sets no cab has still MADE a cab decision: to keep the one
    loaded. Hiding the panel made that silent, and silence reads as 'cabs were
    never considered'."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    body = ui.split("async function renderCabPanel()", 1)[1][:1400]
    assert "UNCHANGED" in body, "no cab action still hides the panel entirely"
    assert "set_type" in body, "it must notice the amp voice changed"


def test_the_planner_can_say_what_cab_it_wants_in_gear_words():
    """The UI reads `currentPlan.cab_need` to find alternatives worth hearing,
    and nothing ever set it, so that query ran on an empty string.

    It matters because IRCommand speaks gear, not artists: measured on the
    owner's library, "steve vai high gain singing lead" scores 0.07 while
    "marshall 4x12 v30 bright lead" scores 0.63. The planner is the piece that
    knows which gear an artist used, so it translates.
    """
    from fm9.planner import PLAN_SCHEMA, plan_shape_line
    spec = PLAN_SCHEMA["properties"]["cab_need"]
    assert "GEAR" in spec["description"]
    assert "NEVER an artist" in spec["description"]
    # and the prompt must advertise the field, or the model never fills it
    assert "cab_need" in plan_shape_line()


def test_the_advertised_shape_cannot_drift_from_the_schema():
    """plan_shape_line derived the ACTION fields but hand-wrote the top level,
    so a new top-level field would be in the schema and absent from the prompt.
    That is the exact drift the function was written to kill, one level up."""
    from fm9.planner import PLAN_SCHEMA, plan_shape_line
    line = plan_shape_line()
    for name in PLAN_SCHEMA["properties"]:
        assert f'"{name}"' in line, f"{name} is in the schema but not the prompt"
