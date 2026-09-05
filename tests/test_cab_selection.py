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
