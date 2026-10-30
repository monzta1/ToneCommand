"""#293: pending asset bytes belong to one test, not a prior module's run."""
import pytest

import server


@pytest.fixture(scope='module')
def previous_download():
    # Module fixtures precede function-scoped isolated_env. This reproduces a
    # previous module's leftover independently of test order or xdist workers.
    stale = {'0' * 40: b'not a real preset or cab file'}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(server, '_install_cache', stale)
        yield stale


@pytest.mark.parametrize('digest', ['1' * 40, '2' * 40])
def test_each_test_owns_a_fresh_pending_download_cache(previous_download, digest):
    assert server._install_cache == {}
    assert server._install_cache is not previous_download
    server._install_cache[digest] = b'this test only'
    assert previous_download == {'0' * 40: b'not a real preset or cab file'}
