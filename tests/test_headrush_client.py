"""The HeadRush transport, tested with no unit on the network (#33 phase 1).

Every test here is named after something that actually went wrong on a
HeadRush Core (fw 5.1.0.2a63755) or in the TypeScript implementation that
preceded this one, and the docstrings say what it cost. That convention is why
these survive renames.

Nothing in this file opens a socket or resolves a name. The resolver and the
HTTP opener are both injected, which is the point of phase 1: a transport that
someone with no HeadRush in the room can review and run.
"""
from __future__ import annotations

import sys

import ast
import errno
import json
import socket
import urllib.error
from pathlib import Path

import pytest

from devices.headrush.client import (
    DEFAULT_ATTEMPTS,
    NOTIFICATION_KINDS,
    _LOSSY_LOOKUP_CODES,
    HeadrushClient,
    _getaddrinfo_resolver,
    describe_unreachable,
    device_origin,
    parse_notification,
    resolve_device_addresses,
)

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "devices" / "headrush" / "client.py"


class RecordingResolver:
    """A resolver that records the family filter it was asked for."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[int | None] = []

    def __call__(self, host, family):
        self.calls.append(family)
        answer = self.answers[min(len(self.calls) - 1, len(self.answers) - 1)]
        if isinstance(answer, BaseException):
            raise answer
        return answer


def _gaierror(code):
    return socket.gaierror(code, "injected")


def _no_sleep(_seconds):
    return None


@pytest.fixture(autouse=True)
def _no_device_env(monkeypatch):
    """Every URL this module builds reads the environment on each call.

    Only one test used to clear it, so running the suite in a shell with
    HEADRUSH_PORT set failed the link-local, v6-bracket, write-shape and
    stale-lease assertions: they were asserting on ambient environment rather
    than on behaviour, and would have looked like real regressions.
    """
    monkeypatch.delenv("HEADRUSH_PORT", raising=False)
    monkeypatch.delenv("HEADRUSH_TIMEOUT_MS", raising=False)


# --- resolution ------------------------------------------------------------

def test_the_first_lookup_asks_for_ipv4_alone_because_the_dual_one_cost_five_seconds():
    """A dual-family lookup waits for both answers. On a LAN where the unit has
    no AAAA, the resolver sat out its full timeout before handing back the A
    record it already had: 5008 ms against 5 ms for the v4-only query, measured
    2026-09-11. Every device call paid it, and the answer was then discarded
    because a v4 address is what gets picked anyway.
    """
    resolver = RecordingResolver([("10.8.72.116", 4)])
    records = resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert records == [("10.8.72.116", 4)]
    assert resolver.calls == [4], "the fast path must not pay for a dual lookup"


def test_a_v6_only_unit_is_still_found_because_the_retry_drops_the_family_filter():
    """The v4-first query is a latency fix, not a v4-only policy. A unit that
    answers only on IPv6 raises a not-found on the filtered try, and if the
    retry kept the filter that unit would be permanently unreachable.
    """
    resolver = RecordingResolver(
        _gaierror(socket.EAI_NONAME),
        [("2001:db8::5", 6)],
    )
    records = resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert records == [("2001:db8::5", 6)]
    assert resolver.calls == [4, None], "the escalation ladder is the retry budget"


_FAMILY_MISS_CODE = next(
    (c for c in (getattr(socket, "EAI_NODATA", None),
                 getattr(socket, "EAI_ADDRFAMILY", None)) if c is not None),
    None,
)


@pytest.mark.skipif(_FAMILY_MISS_CODE is None,
                    reason="this platform defines neither EAI_NODATA nor EAI_ADDRFAMILY")
def test_a_family_miss_on_the_filtered_attempt_drops_the_filter_and_finds_the_unit():
    """Nothing exercised this branch, so deleting it would not have failed.

    The v6-only test injects EAI_NONAME, which is already in the lossy set, so
    it passes with the `attempt == 0 and code in _FAMILY_MISS_CODES` clause
    removed entirely. That clause is the one the comments credit with saving a
    v6-only unit on a platform that tells "no address of this family" apart
    from "no such name", which macOS does not do and Linux does.
    """
    resolver = RecordingResolver(
        socket.gaierror(_FAMILY_MISS_CODE, "no address of that family"),
        [("2001:db8::5", 6)],
    )
    records = resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert records == [("2001:db8::5", 6)]
    assert resolver.calls == [4, None]


@pytest.mark.skipif(_FAMILY_MISS_CODE is None,
                    reason="this platform defines neither EAI_NODATA nor EAI_ADDRFAMILY")
def test_a_family_miss_after_the_filter_is_gone_is_not_retried():
    """A family miss is only ever a verdict on the filter. Once the filter is
    gone the same code means the name really has no address, and retrying it
    just pays the lookup again.

    #186: on Windows this cannot hold, and it is not a bug in the resolver.
    Winsock defines EAI_NODATA as the same number as EAI_NONAME
    (WSAHOST_NOT_FOUND), so "no address of that family" and "no such name,
    try again" are one code there, and a lossy-lookup retry is the right
    reading of it. The test asserts that platform fact first, so a Windows
    where the codes differ fails here rather than passing on a premise that
    no longer holds, then checks the retry still stops within the budget.
    """
    resolver = RecordingResolver(
        socket.gaierror(socket.EAI_NONAME, "dropped"),
        *[socket.gaierror(_FAMILY_MISS_CODE, "no address of that family")] * (DEFAULT_ATTEMPTS + 1),
    )
    collides = _FAMILY_MISS_CODE in _LOSSY_LOOKUP_CODES
    if sys.platform == "win32":
        assert collides, (f"expected EAI_NODATA == EAI_NONAME on Windows, got "
                          f"{_FAMILY_MISS_CODE} vs {socket.EAI_NONAME}")
    with pytest.raises(socket.gaierror):
        resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    if collides:
        assert resolver.calls == [4] + [None] * (DEFAULT_ATTEMPTS - 1), \
            "one code for both: retried as a lossy lookup, and never past the budget"
    else:
        assert resolver.calls == [4, None], "no third attempt after an unfiltered family miss"


def test_a_dropped_mdns_reply_is_retried_rather_than_reported_as_a_dead_device():
    """mDNS is lossy: one lookup in twelve threw not-found with the unit up and
    answering curl the whole time. That single throw used to reach the operator
    as "cannot reach the device" in front of a hardware write.
    """
    resolver = RecordingResolver(
        _gaierror(socket.EAI_NONAME),
        _gaierror(socket.EAI_NONAME),
        [("10.8.72.116", 4)],
    )
    records = resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert records == [("10.8.72.116", 4)]
    assert len(resolver.calls) == 3


def test_the_retry_budget_is_bounded_so_a_unit_that_is_off_does_not_hang_longer():
    """A bogus .local costs 5.005 s per lookup on this machine, so the budget is
    what stands between an absent unit and a 15 s stall becoming a 30 s one.
    After the budget the error is raised as it came, so every caller's existing
    except still means what it meant.
    """
    resolver = RecordingResolver(_gaierror(socket.EAI_NONAME))
    with pytest.raises(socket.gaierror):
        resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert len(resolver.calls) == 3


def test_a_lookup_failure_that_is_not_lossy_is_not_retried_at_all():
    """Paying a real failure three times only makes a broken resolver look
    slower. Only the codes that mean "a reply was dropped" are retried.
    """
    resolver = RecordingResolver(_gaierror(socket.EAI_FAIL))
    with pytest.raises(socket.gaierror):
        resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert len(resolver.calls) == 1


def test_an_empty_answer_escalates_instead_of_being_handed_on_as_an_address():
    """An empty list is not an address. Guarding the injected seam here is
    cheaper than discovering it as an IndexError inside connect().
    """
    resolver = RecordingResolver([], [("10.8.72.116", 4)])
    records = resolve_device_addresses("unit.local", resolve=resolver, sleep=_no_sleep)
    assert records == [("10.8.72.116", 4)]
    # Without this the retry could keep the v4 filter and still pass.
    assert resolver.calls == [4, None]


def test_the_real_resolver_asks_for_the_family_it_was_given_and_dedups(monkeypatch):
    """_getaddrinfo_resolver was never executed by any test, with or without a
    mock, so a family-4 to AF_INET6 swap, a wrong sockaddr index, or a lost
    dedup would all have passed. This pins the production adapter without
    touching the network.
    """
    seen: list[int] = []

    def fake_getaddrinfo(host, port, family):
        seen.append(family)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.8.72.116", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("10.8.72.116", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("fe80::1", 0, 0, 11)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert _getaddrinfo_resolver("unit.local", 4) == [("10.8.72.116", 4), ("fe80::1", 6)]
    assert _getaddrinfo_resolver("unit.local", None) == [("10.8.72.116", 4), ("fe80::1", 6)]
    assert _getaddrinfo_resolver("unit.local", 6) == [("10.8.72.116", 4), ("fe80::1", 6)]
    assert seen == [socket.AF_INET, socket.AF_UNSPEC, socket.AF_INET6]


# --- address selection -----------------------------------------------------

def test_a_link_local_address_falls_back_to_the_hostname_because_no_url_can_use_it():
    """The unit publishes A and AAAA, and which one comes back varies BY
    PROCESS: the shell got IPv4 while the Next server got IPv6 link-local from
    the same name at the same moment.

    The reason for the fallback, stated the way the module states it: a zone has
    no spelling urllib accepts in an http URL. NOT "the lookup does not return a
    zone", which is a Node dns.lookup fact. CPython returns it, measured as
    getaddrinfo("fe80::1%lo0") -> ('fe80::1', 0, 0, 1), and _getaddrinfo_resolver
    discards it deliberately. An earlier draft of this docstring repeated the
    Node claim, which is the sort of unmeasured confidence this project has
    already rejected a change for.
    """
    resolver = RecordingResolver([("fe80::1c2b:3d4e:5f60:7a8b", 6)])
    client = HeadrushClient.connect("unit.local", resolve=resolver, sleep=_no_sleep)
    assert client.address == "unit.local"
    assert client.base_url == "http://unit.local/api/v1"


def test_a_routable_v6_address_is_bracketed_or_every_url_built_from_it_is_malformed():
    """An IPv6 literal without brackets produces a URL that cannot parse, and
    the failure surfaces as the same unhelpful connection error as everything
    else in this area.
    """
    resolver = RecordingResolver([("2001:db8::5", 6)])
    client = HeadrushClient.connect("unit.local", resolve=resolver, sleep=_no_sleep)
    assert client.address == "[2001:db8::5]"
    assert client.base_url == "http://[2001:db8::5]/api/v1"
    assert client.ws_url == "ws://[2001:db8::5]"


def test_ipv4_wins_even_when_the_resolver_lists_a_routable_v6_first():
    """Preferring v4 is what makes the v4-first lookup a pure win rather than a
    guess: the dual answer would have been discarded anyway.
    """
    resolver = RecordingResolver([("2001:db8::5", 6), ("10.8.72.116", 4)])
    client = HeadrushClient.connect("unit.local", resolve=resolver, sleep=_no_sleep)
    assert client.address == "10.8.72.116"


def test_the_name_is_resolved_once_and_reused_for_every_later_request():
    """The OS does not cache mDNS. A .local name costs about 5 s per request
    against about 130 ms of real work, so resolving per call made the device
    panel unusable.
    """
    resolver = RecordingResolver([("10.8.72.116", 4)])
    calls: list[str] = []

    def opener(url, method, body, headers, timeout):
        calls.append(url)
        return b"{}"

    client = HeadrushClient.connect(
        "unit.local", resolve=resolver, sleep=_no_sleep, opener=opener,
    )
    client.subtree()
    client.get_properties("/Evil/Engine/Patch/Chain")
    client.get_properties("/Evil/Engine/Patch/Chain")
    assert resolver.calls == [4], "one lookup for the session, not one per request"
    assert len(calls) == 3


# --- requests --------------------------------------------------------------

def test_a_write_answering_200_with_an_empty_body_is_not_a_parse_error():
    """The unit answers every PUT with 200 and an empty body. Parsing the reply
    as JSON therefore throws on every single write, which is the failure that
    looked like a broken endpoint until someone read the raw response.
    """
    def opener(url, method, body, headers, timeout):
        assert method == "PUT"
        return b""

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    assert client.set_property("/Evil/Engine/Patch/Chain", "Routing", 1) is None


def test_a_write_sends_the_property_as_a_json_object_on_the_object_properties_path():
    """The shape of a write is {"Prop": value} on object-properties, not a
    method call. Getting this wrong is a 404 that reads like an absent device.
    """
    seen: dict = {}

    def opener(url, method, body, headers, timeout):
        seen.update(url=url, method=method, body=body, headers=headers)
        return b""

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    client.set_property("/Evil/Engine/Patch/Chain", "Routing", 3)
    assert seen["url"] == "http://10.8.72.116/api/v1/object-properties/Evil/Engine/Patch/Chain"
    assert seen["method"] == "PUT"
    assert json.loads(seen["body"]) == {"Routing": 3}
    assert seen["headers"]["Content-Type"] == "application/json"


def test_a_failed_request_against_a_stale_lease_retries_on_the_hostname():
    """A leased A record can go stale while the hostname still answers. Pinning
    the address for the session turned a recoverable miss into a dead device.
    """
    attempts: list[str] = []

    def opener(url, method, body, headers, timeout):
        attempts.append(url)
        if url.startswith("http://10.8.72.116"):
            raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        return b'{"ok": true}'

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    assert client.subtree() == {"ok": True}
    assert len(attempts) == 2
    assert attempts[1].startswith("http://unit.local")


def test_a_recovered_fallback_sticks_so_the_dead_address_is_not_paid_for_twice():
    """Retrying once is the criterion; not repeating the failure is the point.

    self.address used to keep pointing at the address we had just proven dead,
    so every later call in the session paid that failure again before falling
    back. With the default 30 s timeout and a unit whose lease moved, that is
    30 s per request for an answer already known to be elsewhere. The original
    retry test used an instant ConnectionRefusedError, so the cost never showed.
    """
    attempts: list[str] = []

    def opener(url, method, body, headers, timeout):
        attempts.append(url)
        if url.startswith("http://10.8.72.116"):
            raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        return b'{"ok": true}'

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    assert client.subtree() == {"ok": True}
    assert client.get_properties("/Evil/Engine/Patch/Chain") == {"ok": True}
    assert client.subtree() == {"ok": True}
    dead = [u for u in attempts if u.startswith("http://10.8.72.116")]
    assert len(dead) == 1, f"paid the dead address {len(dead)} times: {attempts}"
    assert client.address == "unit.local"


def test_the_lease_is_abandoned_even_when_the_hostname_answers_an_error():
    """The two fixes above did not compose, and this is where they met.

    Sticking the hostname only after a fallback that RETURNS means an HTTPError
    from the hostname raises first and the assignment never runs. That is the
    worst case to get wrong: an HTTPError is this module's own evidence that the
    unit is alive, so the pair of facts "the literal is dead" and "the name is
    alive" were both established and then thrown away, and the next call paid
    the dead literal again. The two tests either side of this one each passed
    while the composition was broken (Grok, second review pass).
    """
    attempts: list[str] = []

    def opener(url, method, body, headers, timeout):
        attempts.append(url)
        if url.startswith("http://10.8.72.116"):
            raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    with pytest.raises(urllib.error.HTTPError):
        client.get_properties("/Evil/Engine/Patch")
    assert client.address == "unit.local", "a 404 from the name still proves the lease stale"

    # and the next call must not go near the dead literal again
    attempts.clear()
    with pytest.raises(urllib.error.HTTPError):
        client.get_properties("/Evil/Engine/Patch")
    assert not [u for u in attempts if u.startswith("http://10.8.72.116")]
    assert len(attempts) == 1, "no fallback left to try, so exactly one call"


def test_the_hostname_fallback_does_not_fire_when_the_address_is_already_the_hostname():
    """Retrying the identical URL doubles the wait on a unit that is off, for
    no new information.
    """
    attempts: list[str] = []

    def opener(url, method, body, headers, timeout):
        attempts.append(url)
        raise urllib.error.URLError(ConnectionRefusedError(61, "refused"))

    client = HeadrushClient("unit.local", "unit.local", opener=opener)
    with pytest.raises(urllib.error.URLError):
        client.subtree()
    assert len(attempts) == 1


def test_a_404_from_the_unit_is_not_retried_because_the_unit_already_answered():
    """Observed against the unit on 2026-09-14: reading a container path that
    legitimately 404s cost two round trips for one verdict, because the retry
    caught every exception rather than only the ones that mean nothing
    answered. An HTTPError is the unit replying; the hostname cannot give a
    different answer, and on a .local name the second trip is the expensive
    one. The TypeScript implementation has this defect; this diverges from it.
    """
    attempts: list[str] = []

    def opener(url, method, body, headers, timeout):
        attempts.append(url)
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    client = HeadrushClient("headrushcore.local", "10.8.72.116", opener=opener)
    with pytest.raises(urllib.error.HTTPError):
        client.get_properties("/Evil/Engine/Patch")
    assert len(attempts) == 1, "a reply we did not like is still a reply"


def test_a_method_call_unwraps_the_return_value_the_unit_wraps_it_in():
    """object-method answers {"methodReturnValue": ...}. Handing the envelope
    back to a caller means every call site unwraps it, or forgets to.
    """
    def opener(url, method, body, headers, timeout):
        assert method == "POST"
        assert json.loads(body) == {"arguments": [1, 2]}
        return b'{"methodReturnValue": 7}'

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    assert client.call_method("/Evil/Engine/Patch", "doThing", [1, 2]) == 7


def test_a_non_json_body_is_refused_rather_than_guessed_at():
    """A transport that returns half-parsed rubbish moves the failure to
    whichever caller uses it next.
    """
    def opener(url, method, body, headers, timeout):
        return b"<html>not json</html>"

    client = HeadrushClient("unit.local", "10.8.72.116", opener=opener)
    with pytest.raises(ValueError):
        client.subtree()


def test_the_port_override_is_absent_from_the_url_when_it_is_the_default(monkeypatch):
    """A :80 in the URL is harmless but noisy in every log line and every test
    assertion, and the unit's own editor never writes one.
    """
    monkeypatch.delenv("HEADRUSH_PORT", raising=False)
    assert device_origin("10.8.72.116") == "http://10.8.72.116"
    monkeypatch.setenv("HEADRUSH_PORT", "8080")
    assert device_origin("10.8.72.116") == "http://10.8.72.116:8080"


# --- notifications ---------------------------------------------------------

# The vocabulary is CARRIED FROM the TypeScript client, which was written
# against the unit. It is not transcribed from WebSocket captures on #109,
# because there are none. Labelled rather than implied, so nobody reads this
# list as a hardware measurement.
CARRIED_NOTIFICATION_KINDS = frozenset({
    "propertyValueChanged",
    "objectAdded",
    "objectRemoved",
    "objectPropertyAdded",
    "objectPropertyRemoved",
    "webAccessChanged",
})


def test_the_recognised_vocabulary_is_exactly_the_one_carried_from_the_typescript_client():
    """This is the assertion the per-kind test below cannot make.

    Parametrizing a hardcoded list only proves the parser accepts strings the
    test already named: add a seventh kind to NOTIFICATION_KINDS, or drop one,
    and every such test stays green. Pinning the set itself is what fails when
    the vocabulary drifts.

    Drifts from WHAT, precisely: from the list the TypeScript client carries.
    Nobody has captured WebSocket frames off the Core, #109 has none, and two
    copies of an inherited list can both be wrong against firmware. This test
    pins the two copies to each other and claims nothing more than that.
    """
    assert NOTIFICATION_KINDS == CARRIED_NOTIFICATION_KINDS


@pytest.mark.parametrize("kind", sorted(NOTIFICATION_KINDS))
def test_every_notification_in_the_carried_vocabulary_is_recognised(kind):
    """One kind missing from the set is a change the adapter never hears about.

    Parametrized over the module's own set rather than a copy, so a kind added
    there is actually exercised instead of silently untested. Membership here is
    circular by construction, since parse_notification consults the same set;
    the equality test above is the assertion that is not.

    The vocabulary is the TypeScript client's, not a capture off the unit.
    """
    frame = json.dumps({"notification": kind, "objectPath": "/Evil"})
    assert parse_notification(frame) == {"notification": kind, "objectPath": "/Evil"}


@pytest.mark.parametrize("frame", [
    "not json at all",
    "[]",
    '"a string"',
    "null",
    json.dumps({"notification": "somethingNewInFirmware"}),
    json.dumps({"objectPath": "/Evil"}),
    json.dumps({"notification": 7}),
])
def test_a_frame_that_is_not_a_known_notification_returns_none_rather_than_throwing(frame):
    """The socket carries whatever the firmware decides to send, including
    kinds a later firmware invents. A parse that throws takes the watcher down
    with it.
    """
    assert parse_notification(frame) is None


def test_a_notification_arriving_as_bytes_parses_the_same_as_text():
    """Whether a frame reaches the parser as str or bytes is a property of the
    websocket library, not of the device.
    """
    frame = json.dumps({"notification": "objectAdded", "objectPath": "/Evil"}).encode()
    assert parse_notification(frame) == {"notification": "objectAdded", "objectPath": "/Evil"}


# --- failure classification ------------------------------------------------

def test_a_name_that_did_not_resolve_is_told_apart_from_a_unit_that_is_off():
    """These used to share one sentence, and they need different actions: mDNS
    dropping a reply means try again, a silent address means check the power.
    """
    unresolved = describe_unreachable(
        urllib.error.URLError(socket.gaierror(socket.EAI_NONAME, "not known")),
        "unit.local",
    )
    silent = describe_unreachable(
        urllib.error.URLError(ConnectionRefusedError(61, "refused")), "10.8.72.116",
    )
    assert "did not resolve" in unresolved and "mDNS" in unresolved
    assert "Nothing answered" in silent and "stale address lease" in silent
    assert unresolved != silent


def test_the_units_own_504_is_not_reported_as_nothing_answering():
    """The unit returns 504 Gateway Timeout for a wrong-argument method call.
    A message regex on the word "timeout" classified that as an absent device,
    which sent the operator to check the power on a unit that had just replied.
    """
    error = urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/object-method/Evil/x", 504,
        "Gateway Timeout", {}, None,
    )
    described = describe_unreachable(error, "10.8.72.116")
    assert "504" in described
    assert "Nothing answered" not in described
    assert "did not resolve" not in described


@pytest.mark.parametrize("code,name", [
    (errno.EHOSTUNREACH, "EHOSTUNREACH"),
    (errno.ENETUNREACH, "ENETUNREACH"),
    (errno.ECONNREFUSED, "ECONNREFUSED"),
    (errno.ETIMEDOUT, "ETIMEDOUT"),
])
def test_a_bare_oserror_from_the_network_is_classified_by_its_errno(code, name):
    """The errno set was read off `socket`, which does not define these, so it
    was silently EMPTY and this branch could never fire. No fixture caught it:
    a fixture raises ConnectionRefusedError or TimeoutError, and isinstance
    catches those one line later. The unit caught it. A request to an address
    with no route on the real LAN raises a bare OSError(EHOSTUNREACH) inside a
    URLError, and it was reported as an unclassified failure rather than as a
    device that is not answering (2026-09-14, 10.8.72.199).
    """
    error = urllib.error.URLError(OSError(code, name))
    assert "Nothing answered" in describe_unreachable(error, "10.8.72.199")


def test_a_timeout_with_no_reply_is_the_unit_being_off_not_a_name_problem():
    """A stale DHCP lease blackholes the connection, which surfaces as a
    timeout rather than a refusal and must not be read as a resolver fault.
    """
    described = describe_unreachable(
        urllib.error.URLError(TimeoutError("timed out")), "10.8.72.116",
    )
    assert "Nothing answered" in described


def test_an_unclassified_failure_is_quoted_and_still_ends_a_sentence():
    """A caller appends its own context after this string with a plain space,
    and the unquoted branch was the one that used to run into the next
    sentence.
    """
    described = describe_unreachable(RuntimeError("something odd"), "10.8.72.116")
    assert "something odd" in described
    assert described.endswith(".")


# --- the boundary this phase exists to keep --------------------------------

def test_the_transport_knows_nothing_about_tonecommand():
    """Phase 1 is reviewable by someone with no HeadRush precisely because it
    is transport and nothing else. The moment it imports fm9 or server it stops
    being a thing that can be read on its own, and the adapter's concepts start
    leaking into a layer that should only know HTTP.
    """
    tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = [name for name in imported
                 if name.split(".")[0] in {"fm9", "server", "tools", "service"}]
    assert forbidden == [], f"transport reached into ToneCommand: {forbidden}"


def test_the_transport_declares_no_capabilities_and_implements_no_adapter():
    """Declaring a capability before the adapter exists is a promise nothing
    can keep, and deny-by-default only works if silence stays silence.

    Checked against the parsed identifiers rather than the raw text, because a
    grep also matches the module docstring saying these concepts are absent,
    which is the opposite of a violation and is worth keeping.
    """
    tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            used.add(node.name)
    later = used & {"Capabilities", "DeviceAdapter", "conformance", "Topology",
                    "ReadPath", "SceneSlotState"}
    assert later == set(), f"{sorted(later)} belongs to a later phase"


def test_no_em_dash_in_the_files_this_phase_touched():
    """House style, and the same guard test_device_handle.py keeps."""
    em_dash = chr(0x2014)
    for rel in ("devices/__init__.py", "devices/headrush/__init__.py",
                "devices/headrush/client.py", "tests/test_headrush_client.py",
                # The file this phase is most likely to grow one in, and the
                # guard used to omit it.
                "CHANGELOG.md", "pyproject.toml"):
        assert em_dash not in (ROOT / rel).read_text(encoding="utf-8"), f"em dash in {rel}"


def test_the_changelog_records_this_phase():
    """A transport nobody calls yet is exactly the kind of change that vanishes
    from the record unless it is written down when it lands.
    """
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "devices/headrush/client.py" in text


def test_remote_switched_off_is_a_403_and_is_named_exactly():
    """Measured by toggling HeadRush Remote on a Core with no reboot, 2026-09-15
    (#126). Off: every object-properties and object-meta path answers 403 with
    "DataModel: Web access temporarily disabled" in the body, while `GET /`
    still serves the editor. On: 200 again.

    This is the one unambiguous operator-fixable state, so it gets an exact
    instruction rather than a list of things to check.
    """
    error = urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/object-properties/Evil/Gui", 403,
        "Forbidden", {}, None,
    )
    described = describe_unreachable(error, "10.8.72.116")
    assert "HeadRush Remote" in described
    assert "no reboot" in described
    assert "404" not in described, "403 has one cause; do not muddy it"


def test_a_404_names_its_causes_without_overclaiming():
    """This test previously ASSERTED the bug, which is why it is worth a note.

    It used a subtree URL and required the message to say Remote was not the
    problem. That came from a real correction (Remote off is 403), but it
    overshot: the measured table is path dependent and subtree answers 404 with
    Remote off. Pinning a claim the measurements never supported is what kept
    it alive.

    It now covers the endpoint NOT measured either way, which is the case the
    message must be quietest about.
    """
    described = describe_unreachable(urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/object-method/Evil/API/Rigs/loadRig", 404,
        "Not Found", {}, None), "10.8.72.116")
    assert "404" in described
    assert "no such path" in described, "one cause"
    assert "engine is not running" in described, "and the other"
    assert "was not measured" in described, "and no claim about Remote here"
    assert "Nothing answered" not in described
    assert "did not resolve" not in described


def test_the_subtree_test_is_a_path_segment_not_a_substring():
    """`"/subtree" in url` would take the subtree branch for any path or query
    that merely contained the word."""
    described = describe_unreachable(urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/object-properties/Evil/Gui/subtree-ish", 404,
        "Not Found", {}, None), "10.8.72.116")
    assert "This was a subtree request" not in described
    assert "NOT HeadRush Remote" in described, "it is an object path"


def test_a_certain_cause_instructs_and_an_uncertain_one_only_lists():
    """Both states leave the unit serving its editor page, so an operator
    cannot tell them apart by looking.

    This used to say the messages "must not converge", which stopped describing
    the test once the subtree 404 started naming Remote as one candidate. They
    do both mention Remote now, and should: on a 403 it is the measured cause,
    on a subtree 404 it is one of three. What must not converge is the
    CONFIDENCE. A 403 gives an instruction; a subtree 404 offers candidates and
    a way to discriminate.
    """
    forbidden = describe_unreachable(urllib.error.HTTPError(
        "http://u/api/v1/object-properties/Evil/Gui", 403, "Forbidden", {}, None),
        "unit")
    subtree = describe_unreachable(urllib.error.HTTPError(
        "http://u/api/v1/subtree/Evil/Gui", 404, "Not Found", {}, None), "unit")

    assert "Turn HeadRush Remote on" in forbidden, "certain: instruct"
    assert "Turn HeadRush Remote on" not in subtree, "uncertain: do not instruct"
    assert "HeadRush Remote is off" in subtree, "but do name it as a candidate"
    assert "three causes" in subtree and "tell the last one apart" in subtree


def test_both_measured_object_endpoints_are_covered_not_just_one():
    """`object-meta` is in the measured set the copy names, and only
    `object-properties` was asserted. The set and the claim should match."""
    for endpoint in ("object-properties", "object-meta"):
        described = describe_unreachable(urllib.error.HTTPError(
            f"http://u/api/v1/{endpoint}/Evil/Gui", 404, "Not Found", {}, None),
            "unit")
        assert "NOT HeadRush Remote" in described, endpoint
        assert "answers 403 here" in described, endpoint


def test_a_query_string_does_not_hide_the_endpoint():
    """The segment is taken after stripping query and fragment, or
    `/subtree?x=1` reads as an unknown endpoint and loses the wording this
    whole branch exists to get right."""
    # The URLs must be ones where the strip actually MATTERS. With a path
    # after the endpoint ("/subtree/Evil/Gui?depth=1") the split on "/" already
    # yields "subtree", so an earlier version of this test passed with the fix
    # reverted and proved nothing. These have the query directly on the
    # endpoint, which is the shape the production comment names.
    for url in ("http://u/api/v1/subtree?depth=1",
                "http://u/api/v1/subtree#frag"):
        described = describe_unreachable(urllib.error.HTTPError(
            url, 404, "Not Found", {}, None), "unit")
        assert "This was a subtree request" in described, url


def test_other_http_codes_are_untouched_by_the_403_and_404_branches():
    """The 504 case shares this branch and must keep its own wording."""
    for code, reason in ((504, "Gateway Timeout"), (500, "Internal Server Error")):
        described = describe_unreachable(urllib.error.HTTPError(
            "http://10.8.72.116/api/v1/object-method/Evil/x", code, reason,
            {}, None), "10.8.72.116")
        assert str(code) in described
        assert "HeadRush Remote" not in described


def test_a_404_on_subtree_does_not_rule_remote_out():
    """The measured table is path dependent and the message was not.

    With HeadRush Remote off, `object-properties` and `object-meta` answer 403
    but `subtree` answers 404. So the blanket claim that a 404 means Remote is
    not the problem was wrong for exactly one endpoint, which is the one the
    client's own `subtree()` uses.
    """
    error = urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/subtree/Evil/Gui", 404, "Not Found", {}, None,
    )
    described = describe_unreachable(error, "10.8.72.116")
    assert "HeadRush Remote is off" in described, "subtree 404 can be Remote"
    assert "403 there means Remote" in described, "and how to disambiguate"


def test_a_404_on_an_object_path_still_rules_remote_out():
    """Because there it really is measured to be 403."""
    error = urllib.error.HTTPError(
        "http://10.8.72.116/api/v1/object-properties/Evil/Gui", 404,
        "Not Found", {}, None,
    )
    described = describe_unreachable(error, "10.8.72.116")
    assert "NOT HeadRush Remote" in described
    assert "answers 403 here" in described
