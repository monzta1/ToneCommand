"""Deal the pytest suite across N CI shards, and account for every test (#196).

    pytest tests/ -q -n auto --shard 2/4 --junitxml=shard.xml
        run shard 2 of 4 (0-based), reporting every test it executed
    python tests/shard.py --plan 4 < ids.txt
        print the deal for a collection (pytest --collect-only -q)
    python tests/shard.py --account ids.txt shard-*.xml
        fail unless the shards' reports executed exactly the collection

Whole files, balanced by measured seconds: tests/shard_weights.json holds
each file's total test time from a CI run's JUnit reports (refresh it with
--weights when the balance drifts). A file with no weight yet is costed at
its test count times the median seconds per test, so it still lands
somewhere sensible. The heaviest file goes to the lightest shard first, ties
broken by name, so the deal is identical on every machine and on every
xdist worker. A file is never split, because its module fixtures and
import state were written for one process; -n auto inside each shard evens
out the files that run long for their count.

The deal is a partition by construction, and tests/test_shard.py proves it.
CI then proves it on the real suite: the account compares what the shards
EXECUTED (their JUnit reports, which xdist's controller writes once) with a
full collection, so a test that ran nowhere, ran twice, or ran without being
collected fails the required check instead of passing quietly.
"""
from __future__ import annotations

import json
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

WEIGHTS = Path(__file__).resolve().with_name("shard_weights.json")


def parse(spec: str) -> tuple[int, int]:
    """'I/N' -> (I, N), 0 <= I < N."""
    try:
        index, total = (int(x) for x in str(spec).split("/"))
    except ValueError:
        raise ValueError(f"--shard wants I/N, for example 0/4, not {spec!r}") from None
    if total < 1 or not 0 <= index < total:
        raise ValueError(f"--shard {spec}: I must be from 0 to N-1 and N at least 1")
    return index, total


def load_weights() -> dict[str, float]:
    try:
        return json.loads(WEIGHTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def costs(counts: dict[str, int], weights: dict[str, float] | None = None) -> dict[str, float]:
    """Seconds per file: measured where known, else count times the median
    seconds per test of the measured files (1.0 with no measurements)."""
    weights = weights or {}
    rates = [weights[f] / counts[f] for f in counts if f in weights and counts[f] and weights[f] > 0]
    per_test = statistics.median(rates) if rates else 1.0
    return {f: float(weights[f]) if f in weights else counts[f] * per_test for f in counts}


def deal(counts: dict[str, int], total: int,
         weights: dict[str, float] | None = None) -> list[list[str]]:
    """Files to shards: heaviest first, each to the currently lightest shard
    (lowest index on a tie). Without weights the cost is the test count."""
    cost = costs(counts, weights) if weights else {f: float(c) for f, c in counts.items()}
    shards: list[list[str]] = [[] for _ in range(total)]
    load = [0.0] * total
    for name in sorted(cost, key=lambda f: (-cost[f], f)):
        i = min(range(total), key=lambda k: (load[k], k))
        shards[i].append(name)
        load[i] += cost[name]
    return shards


def weights_from(report_paths) -> dict[str, float]:
    """Each test file's total seconds from JUnit reports."""
    out: Counter = Counter()
    for path in report_paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            module = case.get("classname", "").split(".")[1]
            out[f"tests/{module}.py"] += float(case.get("time") or 0)
    return {k: round(v, 2) for k, v in sorted(out.items())}


def file_of(nodeid: str) -> str:
    return nodeid.split("::", 1)[0]


def counts_of(nodeids) -> dict[str, int]:
    return dict(Counter(file_of(n) for n in nodeids))


def junit_key(classname: str, name: str) -> str:
    """One executed test as a comparable key: JUnit's dotted classname
    (tests.test_x or tests.test_x.TestClass) plus the test name."""
    return f"{classname}::{name}"


def nodeid_key(nodeid: str) -> str:
    """A collected node id in the same shape junit_key produces:
    tests/test_x.py::TestClass::test_y[p] -> tests.test_x.TestClass::test_y[p]."""
    # A parameter id may itself contain "::" (an IPv6 URL such as
    # http://[::1]:8770), so the parameters come off before the split.
    base, bracket, params = nodeid.partition("[")
    parts = base.split("::")
    module = parts[0][:-3] if parts[0].endswith(".py") else parts[0]
    dotted = module.replace("\\", "/").replace("/", ".")
    return junit_key(".".join([dotted, *parts[1:-1]]), parts[-1] + bracket + params)


def executed(report_paths) -> list[str]:
    """Every testcase in the JUnit reports, skipped ones included (a skip
    ran and decided to skip; it was not dropped)."""
    out = []
    for path in report_paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            out.append(junit_key(case.get("classname", ""), case.get("name", "")))
    return out


def account(collected: list[str], ran: list[str]) -> tuple[list[str], list[str], list[str]]:
    """(missing, duplicated, extra): collected but never run, run more than
    once, run but never collected. All three empty is the only pass."""
    want = {nodeid_key(n) for n in collected}
    seen = Counter(ran)
    missing = sorted(want - set(seen))
    duplicated = sorted(k for k, c in seen.items() if c > 1)
    extra = sorted(set(seen) - want)
    return missing, duplicated, extra


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--plan":
        ids = [line.strip() for line in sys.stdin if "::" in line]
        counts = counts_of(ids)
        cost = costs(counts, load_weights())
        for i, files in enumerate(deal(counts, int(argv[1]), load_weights())):
            print(f"shard {i}: {sum(counts[f] for f in files)} tests, "
                  f"{sum(cost[f] for f in files):.0f} s in {len(files)} files")
        return 0
    if len(argv) >= 2 and argv[0] == "--weights":
        WEIGHTS.write_text(json.dumps(weights_from(argv[1:]), indent=1, sort_keys=True) + "\n",
                           encoding="utf-8")
        return 0
    if len(argv) >= 3 and argv[0] == "--account":
        with open(argv[1], encoding="utf-8") as f:
            collected = [line.strip() for line in f if "::" in line]
        missing, duplicated, extra = account(collected, executed(argv[2:]))
        for label, items in (("never ran", missing), ("ran twice", duplicated),
                             ("ran without being collected", extra)):
            for item in items[:50]:
                print(f"{label}: {item}")
        print(f"collected {len(collected)}, reports {len(argv) - 2}: "
              f"{len(missing)} missing, {len(duplicated)} duplicated, {len(extra)} extra")
        return 1 if (missing or duplicated or extra) else 0
    print(__doc__.split("\n\n")[1])
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
