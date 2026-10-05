"""#196: the shard dealer and the account that proves no test was dropped."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("tonecommand_test_shard", HERE / "shard.py")
shard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shard)

COUNTS = {"tests/test_a.py": 40, "tests/test_b.py": 33, "tests/test_c.py": 30,
          "tests/test_d.py": 12, "tests/test_e.py": 9, "tests/test_f.py": 1,
          "tests/test_g.py": 1}


@pytest.mark.parametrize("total", [1, 2, 3, 4, 7, 10])
def test_the_deal_is_an_exact_partition(total):
    shards = shard.deal(COUNTS, total)
    assert len(shards) == total
    dealt = [f for s in shards for f in s]
    assert sorted(dealt) == sorted(COUNTS)            # every file, once
    assert len(dealt) == len(set(dealt))


def test_the_deal_is_deterministic_whatever_the_input_order():
    reordered = dict(reversed(list(COUNTS.items())))
    assert shard.deal(COUNTS, 4) == shard.deal(reordered, 4)


def test_the_deal_is_balanced_within_one_file():
    """Greedy heaviest-first onto the lightest shard: the heaviest shard is
    never more than the largest file above the lightest."""
    for total in (2, 3, 4):
        loads = [sum(COUNTS[f] for f in s) for s in shard.deal(COUNTS, total)]
        assert max(loads) - min(loads) <= max(COUNTS.values())
    loads = [sum(COUNTS[f] for f in s) for s in shard.deal(COUNTS, 3)]
    assert sorted(loads) == [42, 42, 42]       # 40+1+1, 33+9, 30+12


@pytest.mark.parametrize("bad", ["4/4", "-1/4", "0/0", "x", "1-4", ""])
def test_a_bad_shard_spec_is_refused(bad):
    with pytest.raises(ValueError):
        shard.parse(bad)


def test_nodeid_and_junit_keys_meet():
    assert shard.nodeid_key("tests/test_x.py::test_y[a-1]") == "tests.test_x::test_y[a-1]"
    assert shard.nodeid_key("tests/test_x.py::TestK::test_y") == "tests.test_x.TestK::test_y"
    assert shard.nodeid_key("tests\\test_x.py::test_y") == "tests.test_x::test_y"
    # found by the first sharded CI run: a parameter id holding "::"
    assert shard.nodeid_key("tests/test_x.py::test_y[http://[::1]:8770]") == \
        "tests.test_x::test_y[http://[::1]:8770]"


def test_account_passes_only_an_exact_execution():
    collected = ["tests/test_x.py::test_a", "tests/test_x.py::TestK::test_b"]
    good = ["tests.test_x::test_a", "tests.test_x.TestK::test_b"]
    assert shard.account(collected, good) == ([], [], [])


def test_account_reports_a_test_that_never_ran():
    missing, dup, extra = shard.account(
        ["tests/test_x.py::test_a", "tests/test_x.py::test_b"], ["tests.test_x::test_a"])
    assert missing == ["tests.test_x::test_b"] and dup == [] and extra == []


def test_account_reports_a_test_that_ran_twice():
    missing, dup, extra = shard.account(
        ["tests/test_x.py::test_a"], ["tests.test_x::test_a", "tests.test_x::test_a"])
    assert dup == ["tests.test_x::test_a"] and missing == [] and extra == []


def test_account_reports_a_test_that_ran_without_being_collected():
    missing, dup, extra = shard.account(
        ["tests/test_x.py::test_a"], ["tests.test_x::test_a", "tests.test_x::test_z"])
    assert extra == ["tests.test_x::test_z"]


def test_account_command_fails_on_a_missing_test(tmp_path):
    ids = tmp_path / "ids.txt"
    ids.write_text("tests/test_x.py::test_a\ntests/test_x.py::test_b\n", encoding="utf-8")
    report = tmp_path / "r.xml"
    report.write_text('<testsuites><testsuite><testcase classname="tests.test_x" name="test_a"/>'
                      '</testsuite></testsuites>', encoding="utf-8")
    assert shard.main(["--account", str(ids), str(report)]) == 1


def test_a_real_junit_report_accounts_against_a_real_collection(tmp_path):
    """Pytest's own node ids and its own JUnit report, for a module test, a
    class test, a parametrized test and a skip, meet exactly."""
    proj = tmp_path / "proj"
    (proj / "tests").mkdir(parents=True)
    (proj / "tests" / "test_demo.py").write_text(
        "import pytest\n"
        "def test_plain():\n    pass\n"
        "class TestK:\n    def test_in_class(self):\n        pass\n"
        "@pytest.mark.parametrize('v', [1, 'a-b'])\ndef test_param(v):\n    pass\n"
        "@pytest.mark.skip(reason='skips still ran')\ndef test_skipped():\n    pass\n",
        encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *a],
                                    cwd=proj, capture_output=True, text=True)
    ids = [l for l in run("--collect-only", "tests").stdout.splitlines() if "::" in l]
    assert len(ids) == 5
    run("tests", f"--junitxml={tmp_path / 'r.xml'}")
    assert shard.account(ids, shard.executed([tmp_path / "r.xml"])) == ([], [], [])


def test_the_shard_option_splits_the_real_suite_exactly():
    """The conftest hook, on this repository's own suite: four shards'
    collections are disjoint and together are the whole collection."""
    def collect(*extra):
        out = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q", "--collect-only",
                              "-p", "no:cacheprovider", *extra],
                             cwd=HERE.parent, capture_output=True, text=True)
        return [l for l in out.stdout.splitlines() if "::" in l]
    whole = collect()
    parts = [collect("--shard", f"{i}/4") for i in range(4)]
    assert all(parts)
    union = [n for p in parts for n in p]
    assert sorted(union) == sorted(whole) and len(union) == len(set(union))
