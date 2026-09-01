"""Sharing that cannot lose a recipe, whatever the network is doing.

Moncy set the constraint before the design existed: nothing a person writes
may be lost because a service was unreachable. That inverts the usual shape,
where a POST is the event and local state is a cache of it. Here the local
file IS the event, and the service is a place copies go.
"""
import json

import pytest

from fm9 import share


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TONECOMMAND_OUTBOX", str(tmp_path / "outbox.json"))
    monkeypatch.delenv("TONECOMMAND_SHARE_URL", raising=False)


# --- nothing is lost, whatever happens -----------------------------------

def test_with_no_service_the_work_is_still_queued():
    """Local only is a normal state, not a failure, and the one a fresh
    checkout starts in."""
    share.queue("recipe", {"name": "mine"})
    out = share.sync()
    assert out["endpoint"] is None and out["pending"] == 1
    assert "stay local" in out["why"]
    assert len(share.pending()) == 1


def test_a_dead_service_leaves_everything_queued(monkeypatch):
    monkeypatch.setenv("TONECOMMAND_SHARE_URL", "http://127.0.0.1:1/nope")
    share.queue("recipe", {"name": "mine"})
    share.queue("use", {"name": "mine"})
    out = share.sync(timeout=0.4)
    assert out["sent"] == 0 and out["failed"] == 2
    assert len(share.pending()) == 2, "a failed send must never drop the entry"
    assert all(e["attempts"] == 1 for e in share.pending())


def test_only_an_explicit_success_clears_an_entry(monkeypatch):
    """A recipe that might not have arrived is worth sending twice. Losing one
    is not worth avoiding a duplicate."""
    calls = {"n": 0}

    class Resp:
        status = 500
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setenv("TONECOMMAND_SHARE_URL", "http://example.invalid")
    monkeypatch.setattr(share.urllib.request, "urlopen",
                        lambda *a, **k: (calls.update(n=calls["n"] + 1), Resp())[1])
    share.queue("recipe", {"name": "mine"})
    share.sync()
    assert len(share.pending()) == 1
    assert share.pending()[0]["last_error"] == "HTTP 500"


def test_a_corrupt_outbox_does_not_take_the_recipes_with_it(tmp_path, monkeypatch):
    """The files in recipes/ are the work. This is only the record of what has
    been sent, so a broken record must fail quietly and start again."""
    p = tmp_path / "outbox.json"
    p.write_text("{ not json")
    monkeypatch.setenv("TONECOMMAND_OUTBOX", str(p))
    assert share.pending() == []
    share.queue("recipe", {"name": "still works"})
    assert len(share.pending()) == 1


def test_the_outbox_is_written_atomically(tmp_path, monkeypatch):
    """A crash mid write must not truncate the queue."""
    import inspect
    src = inspect.getsource(share._write)
    assert ".replace(" in src and "tmp" in src


def test_trimming_never_touches_what_is_still_waiting():
    for i in range(5):
        e = share.queue("use", {"name": f"r{i}"})
    data = share._read()
    for e in data["entries"][:3]:
        e["accepted"] = True
    share._write(data)
    share.forget_accepted(keep=1)
    assert len(share.pending()) == 2, "pending entries are never trimmed"


# --- what gets counted ----------------------------------------------------

def test_a_play_carries_its_own_id():
    """So retrying a send that failed halfway cannot count the same play
    twice, while retrying stays safe."""
    import server
    from fastapi.testclient import TestClient
    c = TestClient(server.app)
    c.post("/api/share/used", json={"name": "some-tone"})
    entries = [e for e in share.pending() if e["kind"] == "use"]
    assert entries and entries[0]["payload"]["id"]


def test_the_ui_counts_a_transmit_not_a_download():
    """The app knows when a recipe actually reached hardware, which is a much
    better signal than a fetch and far harder to inflate by refreshing."""
    from pathlib import Path
    ui = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text()
    script = ui.split("<script>")[1]
    apply_fn = script.split("async function apply()")[1].split("\n}\n")[0]
    assert "/api/share/used" in apply_fn
    assert "out.results.some(x => x.ok)" in apply_fn, \
        "a failed transmit is not a play"
    # and the browser never posts a play merely for listing one
    use_fn = script.split("async function useRecipe")[1].split("\n}\n")[0]
    assert "/api/share/used" not in use_fn


# --- ranking is a nicety, never a dependency ------------------------------

def test_the_catalogue_renders_without_the_counter(monkeypatch):
    """A catalogue that will not load because a counter is down is a broken
    tool."""
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(share, "fetch_stats",
                        lambda timeout=4.0: ({}, "counter unreachable"))
    d = TestClient(server.app).get("/api/recipes").json()
    assert d["ranked"] is False
    assert isinstance(d["recipes"], list)


def test_ranking_uses_recent_plays_not_a_lifetime_total(monkeypatch):
    """A lifetime total ranks by age, so a good new tone could never surface."""
    import server
    from fastapi.testclient import TestClient
    monkeypatch.setattr(share, "fetch_stats", lambda timeout=4.0: (
        {"goodbye-yesterday-rock-intro": {"plays": 500, "recent": 0},
         "steve-lukather-lead": {"plays": 3, "recent": 3}}, None))
    d = TestClient(server.app).get("/api/recipes").json()
    order = [r["name"] for r in d["recipes"]]
    assert order.index("steve-lukather-lead") < order.index("goodbye-yesterday-rock-intro")


# --- the endpoint has to be findable where the docs say to put it ---------

def test_the_endpoint_is_read_from_the_env_file_too(tmp_path, monkeypatch):
    """Every other setting in this project lives in `.env`, and the service
    README says to set this one the same way. Reading only os.environ meant
    following those instructions left the feature silently dark: recipes queue
    in the outbox forever while the app reports no endpoint, with nothing
    anywhere saying why. Found by deploying the service and watching the app
    ignore it.
    """
    from fm9 import share
    monkeypatch.delenv("TONECOMMAND_SHARE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text("OTHER=ignored\nTONECOMMAND_SHARE_URL=https://example.workers.dev\n")
    monkeypatch.setattr(share, "_env_path", lambda: env)
    assert share.endpoint() == "https://example.workers.dev"


def test_the_environment_outranks_the_file(tmp_path, monkeypatch):
    """An explicit export is an operator pin, the same rule the store
    whitelist follows."""
    from fm9 import share
    env = tmp_path / ".env"
    env.write_text("TONECOMMAND_SHARE_URL=https://from-file.example\n")
    monkeypatch.setattr(share, "_env_path", lambda: env)
    monkeypatch.setenv("TONECOMMAND_SHARE_URL", "https://from-env.example")
    assert share.endpoint() == "https://from-env.example"


def test_a_trailing_slash_is_dropped(monkeypatch):
    """Routes are appended as "/submit", so a trailing slash would give
    "//submit"."""
    from fm9 import share
    monkeypatch.setenv("TONECOMMAND_SHARE_URL", "https://x.example/")
    assert share.endpoint() == "https://x.example"


def test_the_file_parser_handles_quotes_and_trailing_comments(tmp_path,
                                                              monkeypatch):
    from fm9 import share
    monkeypatch.delenv("TONECOMMAND_SHARE_URL", raising=False)
    env = tmp_path / ".env"
    env.write_text(
        'TONECOMMAND_SHARE_URL="https://quoted.example"  # deployed today\n')
    monkeypatch.setattr(share, "_env_path", lambda: env)
    assert share.endpoint() == "https://quoted.example"


def test_a_missing_env_file_is_not_an_error(tmp_path, monkeypatch):
    """A fresh checkout has none, and sharing is local only, which is a
    supported state rather than a fault."""
    from fm9 import share
    monkeypatch.delenv("TONECOMMAND_SHARE_URL", raising=False)
    monkeypatch.setattr(share, "_env_path", lambda: tmp_path / "nope.env")
    assert share.endpoint() == ""
