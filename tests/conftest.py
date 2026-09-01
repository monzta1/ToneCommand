import os
import sys
from pathlib import Path

# CI runs `pytest tests/ -q`, and the bare pytest entry point does NOT put the
# working directory on sys.path the way `python -m pytest` does. tools/ is not
# an installed package (pyproject ships fm9 and server only), so importing a
# tool in a test fails at collection without this. Doing it in conftest also
# removes an accidental dependency on collection order: a module-scope import
# of tools used to work only if some earlier test module had already inserted
# the root as a side effect.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# Tests run with a configured store range (the empty-default behavior has
# its own dedicated tests in test_store_config.py).
os.environ.setdefault("TONECOMMAND_STORE_SLOTS", "133-148")


import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Never read the developer's real .env, in ANY test module.

    _env falls back to that file when a variable is ABSENT, so a real line
    still reaches a test that has not deleted the variable. This lived in one
    test module first, where an autouse fixture covers only that module: the
    openai and grok suites stayed exposed, and with a realistic .env present
    they read PLANNER_BASE_URL out of it and opened a connection - at a live
    CLIProxyAPI on 8317, that means POSTing the test prompt at the real
    router. Belongs here, where it covers every module.

    Every variable the planner reads has to be in the list below. The two
    Claude model variables were added by this PR and left out of it, so a
    developer with CLAUDE_CLI_MODEL exported got a false failure from the
    test asserting the built-in default - the same ambient-env leak, one PR
    later.
    """
    from fm9 import planner, share
    monkeypatch.setattr(planner, "_env_path", lambda: tmp_path / ".env")
    # Third time, same lesson. share.endpoint() gained a .env fallback the day
    # the service was deployed, because reading only os.environ meant the
    # documented setup left sharing silently dark. Within a minute a test
    # asserting "no service, work is queued locally" was reading the
    # developer's live endpoint out of the real file. Any module that falls
    # back to .env belongs in this fixture the moment it gains the fallback.
    monkeypatch.setattr(share, "_env_path", lambda: tmp_path / ".env")
    monkeypatch.delenv("TONECOMMAND_SHARE_URL", raising=False)
    # The same lesson, one file later. store_slots.json is the boundary that
    # decides which of the owner's 512 presets may be overwritten, and tests
    # that exercise the endpoint were isolating it one by one. A test that
    # forgot wrote to the real file, and the suite twice widened Moncy's live
    # whitelist to every slot on the unit, paid content included. Relying on
    # each test to remember is the wrong shape for a safety boundary, so it
    # is pinned here for every module whether the test asks or not.
    monkeypatch.setenv("TONECOMMAND_STORE_SLOTS_FILE",
                       str(tmp_path / "store_slots.json"))
    for name in ("PLANNER_BACKEND", "PLANNER_BASE_URL", "PLANNER_MODEL",
                 "PLANNER_API_KEY", "PLANNER_TIMEOUT", "PLANNER_MAX_TOKENS",
                 "GROK_CLI_MODEL", "ANTHROPIC_API_KEY",
                 "CLAUDE_CLI_MODEL", "CLAUDE_API_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / ".env"
