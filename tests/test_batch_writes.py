"""Batched parameter verification (issue #47 lever 2): write a block's params in
a burst, then verify them ALL with a single settle + read instead of a settle
loop per param. The guarantee this suite protects: every param is still
verified, a dropped write still fails, and a straggler is retried on the full
single-param path, so batching is a speed change and never a safety change.
"""
from fm9.device import SetResult
from fm9.registry import Registry
from fm9.sim import SimFM9


def dev():
    return SimFM9(Registry())


def _specs(reg, names):
    out = []
    for (fam, pid), pd in reg.params.items():
        if fam == "DISTORT" and pd.get("name") in names:
            out.append(reg.spec("DISTORT", pid, 1))
    return out


DRIVE_BASS_MID = ["DISTORT_DRIVE", "DISTORT_BASS", "DISTORT_MID"]


def test_a_batch_writes_and_verifies_every_param():
    reg = Registry()
    with dev() as d:
        d.select_preset(0)
        specs = _specs(reg, DRIVE_BASS_MID)
        items = [(s, 6.0) for s in specs]
        results = d.set_params_batch(items)
        assert len(results) == len(specs)
        assert all(r.ok for r in results), [r.detail for r in results]
        assert all(abs(r.display_after - 6.0) <= 0.05 for r in results)
        assert all("batched" in r.detail for r in results)


def test_the_batch_reads_once_to_verify_not_once_per_param():
    """The whole point: N writes, then ONE read that checks them all, versus a
    settle-and-read loop per param."""
    reg = Registry()
    with dev() as d:
        d.select_preset(0)
        specs = _specs(reg, DRIVE_BASS_MID)
        calls = {"n": 0}
        real = d.bulk_read
        d.bulk_read = lambda eid, **k: (calls.__setitem__("n", calls["n"] + 1)
                                        or real(eid, **k))
        d.set_params_batch([(s, 4.0) for s in specs])
        # before + after = 2, independent of how many params were written
        assert calls["n"] == 2, f"expected 2 bulk reads, got {calls['n']}"


def test_a_write_that_does_not_land_is_retried_on_the_full_path():
    """Force the batch verify to see nothing (empty after-read); every param
    must then fall through to set_param_display, so none is falsely passed."""
    reg = Registry()
    with dev() as d:
        d.select_preset(0)
        specs = _specs(reg, DRIVE_BASS_MID)
        retried = []
        d.set_param_display = lambda spec, val: (retried.append(spec.name)
                                                 or SetResult(True, "retry", None, val))
        # after-read returns empty so the batch cannot verify anything
        seq = {"n": 0}
        real = d.bulk_read

        def flaky(eid, **k):
            seq["n"] += 1
            return [] if seq["n"] >= 2 else real(eid, **k)  # 1st=before ok, 2nd=after empty
        d.bulk_read = flaky
        results = d.set_params_batch([(s, 3.0) for s in specs])
        assert retried == [s.name for s in specs], "unverified writes must be retried"
        assert all(r.ok for r in results)


def test_batch_matches_single_param_writes():
    """Same values, two paths, same landed result."""
    reg = Registry()
    with dev() as d:
        d.select_preset(0)
        specs = _specs(reg, DRIVE_BASS_MID)
        batch = {s.name: r for s, r in
                 zip(specs, d.set_params_batch([(s, 7.0) for s in specs]))}
    with dev() as d2:
        d2.select_preset(0)
        single = {}
        for s in _specs(reg, DRIVE_BASS_MID):
            r = d2.set_param_display(s, 7.0)
            single[s.name] = r
    for name in batch:
        assert batch[name].ok == single[name].ok
        assert abs(batch[name].display_after - single[name].display_after) <= 0.05


def test_an_empty_batch_is_a_noop():
    with dev() as d:
        assert d.set_params_batch([]) == []


# --- the apply-loop wiring (flag-gated), server level ---

import pytest
from fastapi.testclient import TestClient
import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "_fm9", SimFM9(server.reg))
    return TestClient(server.app)


def _amp_params(v1=5, v2=4, v3=6):
    return {"actions": [
        {"kind": "set_scene", "value": 1},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_DRIVE", "value": v1},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_BASS", "value": v2},
        {"kind": "set_param", "block": "amp", "param": "DISTORT_MID", "value": v3}]}


def test_a_run_of_same_block_params_batches_when_enabled(client, monkeypatch):
    monkeypatch.setattr(server, "_BATCH_WRITES", True)
    calls = {"n": 0}
    real = server._fm9.set_params_batch
    monkeypatch.setattr(server._fm9, "set_params_batch",
                        lambda items: (calls.__setitem__("n", calls["n"] + 1)
                                       or real(items)))
    d = client.post("/api/apply", json=_amp_params()).json()
    res = [r for r in d["results"]
           if (r.get("action") or {}).get("kind") == "set_param"]
    assert len(res) == 3 and all(r["ok"] for r in res), res
    assert calls["n"] >= 1, "the run of three set_params should have batched"
    assert res[0]["after"] == 5 and res[2]["after"] == 6


def test_flag_off_never_batches(client, monkeypatch):
    monkeypatch.setattr(server, "_BATCH_WRITES", False)
    calls = {"n": 0}
    monkeypatch.setattr(server._fm9, "set_params_batch",
                        lambda items: calls.__setitem__("n", calls["n"] + 1))
    d = client.post("/api/apply", json=_amp_params()).json()
    res = [r for r in d["results"]
           if (r.get("action") or {}).get("kind") == "set_param"]
    assert len(res) == 3 and all(r["ok"] for r in res)
    assert calls["n"] == 0, "with the flag off the batch path must not run"


def test_batched_and_single_paths_land_the_same_values(client, monkeypatch):
    monkeypatch.setattr(server, "_BATCH_WRITES", True)
    on = client.post("/api/apply", json=_amp_params(7, 3, 8)).json()["results"]
    monkeypatch.setattr(server, "_BATCH_WRITES", False)
    off = client.post("/api/apply", json=_amp_params(7, 3, 8)).json()["results"]
    def afters(rows):
        return {r["action"]["param"]: r.get("after") for r in rows
                if (r.get("action") or {}).get("kind") == "set_param"}
    assert afters(on) == afters(off)
