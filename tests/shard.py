"""Deal the pytest suite across N CI shards, and account for every test (#196).

    pytest tests/ -q -n auto --shard 2/4 --junitxml=shard.xml
        run shard 2 of 4 (0-based), reporting every test it executed
    python tests/shard.py --plan 4 < ids.txt
        print the deal for a collection (pytest --collect-only -q)
    python tests/shard.py --account ids.txt shard-*.xml
        fail unless the shards' reports executed exactly the collection

Whole files, count-balanced: the heaviest file goes to the lightest shard
first, ties broken by name, so the deal is identical on every machine and on
every xdist worker. A file is never split, because its module fixtures and
import state were written for one process; -n auto inside each shard evens
out the files that run long for their count.

The deal is a partition by construction, and tests/test_shard.py proves it.
CI then proves it on the real suite: the account compares what the shards
EXECUTED (their JUnit reports, which xdist's controller writes once) with a
full collection, so a test that ran nowhere, ran twice, or ran without being
collected fails the required check instead of passing quietly.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from collections import Counter


def parse(spec: str) -> tuple[int, int]:
    """'I/N' -> (I, N), 0 <= I < N."""
    try:
        index, total = (int(x) for x in str(spec).split("/"))
    except ValueError:
        raise ValueError(f"--shard wants I/N, for example 0/4, not {spec!r}") from None
    if total < 1 or not 0 <= index < total:
        raise ValueError(f"--shard {spec}: I must be from 0 to N-1 and N at least 1")
    return index, total


def deal(counts: dict[str, int], total: int) -> list[list[str]]:
    """Files to shards: heaviest first, each to the currently lightest shard
    (lowest index on a tie)."""
    shards: list[list[str]] = [[] for _ in range(total)]
    load = [0] * total
    for name in sorted(counts, key=lambda f: (-counts[f], f)):
        i = min(range(total), key=lambda k: (load[k], k))
        shards[i].append(name)
        load[i] += counts[name]
    return shards


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
        for i, files in enumerate(deal(counts, int(argv[1]))):
            print(f"shard {i}: {sum(counts[f] for f in files)} tests in {len(files)} files")
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
