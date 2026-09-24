"""One repo-wide em dash guard.

CLAUDE.md says it plainly: no em dash anywhere, in code, comments, docs or
commit messages. Enforcement did not match. SEVEN separate guards each carried
a hardcoded list of "the files this phase touched" (plus one inline assertion
in test_capture_intent.py), which is a fine contract for a phase and a bad one
for a repo rule: between them they left
`docs/UI-REDESIGN-SPEC.md` (17) and
`docs/CLAUDE-CODE-UI-IMPLEMENTATION-PROMPT.md` (5) unguarded from the start,
and nothing would have caught the next file either.

This walks every tracked text file instead, so a new file is covered by
existing, not by somebody remembering to extend a list. The per-phase guards
are left alone: they assert something narrower and they are not wrong.

NOTHING HERE SKIPS QUIETLY

A check that stops checking when its input is awkward reports green while
testing nothing, and it is the shape hardest to notice because nothing looks
wrong anywhere. So there are exactly two reasons a tracked file is not read,
both narrow and both stated: a suffix in `BINARY`, which is a file that was
never text, and `config/fm9_catalog.json`, which this project may not edit.
Every other file must be readable as UTF-8 and is scanned. A file that cannot
be decoded FAILS rather than being passed over, because "we could not read it"
and "it is clean" are different answers.
"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EM_DASH = chr(0x2014)          # spelled, so this file is not a hit itself

#: Path -> why this project may not rewrite it. Not "why the em dash is fine".
WHOLE_FILE_EXEMPT = {
    "config/fm9_catalog.json":
        "copied verbatim from mcp-midi-control's "
        "packages/fractal-midi/catalog/fm9.json. config/README.md says to "
        "refresh from the upstream catalog rather than hand-edit it, so a "
        "punctuation change here would be a silent local fork of a file whose "
        "whole value is being unmodified.",
}

#: Path -> (the heading the quoted block follows, why it is quoted).
#: Only the fenced block under that heading is exempt. The REST of the file is
#: this project's own prose and is checked like anything else: excluding a
#: whole file because one quoted region needs it leaves the rest unguarded.
QUOTED_BLOCKS = {
    "THIRD_PARTY_NOTICES.md": (
        "Reproduction of that project's NOTICE (as required by Apache-2.0):",
        "Apache-2.0 section 4 requires that NOTICE be reproduced, and "
        "reproducing it means reproducing it, punctuation included.",
    ),
}

#: Suffixes that were never text. Skipping these is not "could not read it".
#: `.bin` is here because the fail-closed read FOUND the three fixtures the
#: earlier skip-on-decode-error version was quietly passing over.
BINARY = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".syx", ".woff",
          ".woff2", ".ttf", ".zip", ".wav", ".nam", ".bin"}


def tracked_files():
    """Every tracked path, from git, because "tracked" is git's word.

    FAILS rather than skips when git is unavailable. CI runs this from an
    `actions/checkout` work tree, so the only way into these paths is running
    the suite somewhere it was never meant to run, and that should say so.
    """
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
    except FileNotFoundError:
        raise AssertionError(
            "this guard needs a git work tree to know what is tracked, and "
            "git is not on PATH. It fails rather than skipping on purpose: a "
            "check that disables itself when its input is missing reports "
            "green while testing nothing.") from None
    except subprocess.CalledProcessError as err:
        raise AssertionError(
            f"`git ls-files` failed in {ROOT}, so the set of tracked files is "
            f"unknown and this guard cannot run: "
            f"{(err.stderr or '').strip()[:200]}") from None
    return [rel for rel in out.split("\0") if rel]


def strip_quoted_block(text: str, heading: str) -> tuple[str, str]:
    """Split `text` into (everything else, the fenced block under `heading`).

    Returns ("", "") for the quoted part when the heading or its fence is
    gone, so the caller can fail on a stale exemption rather than silently
    exempting nothing (or, worse, the wrong region).
    """
    if heading not in text:
        return text, ""
    before, _, after = text.partition(heading)
    opened = after.find("\n```")
    if opened == -1:
        return text, ""
    closed = after.find("\n```", opened + 1)
    if closed == -1:
        return text, ""
    quoted = after[opened:closed + 4]
    return before + after[:opened] + after[closed + 4:], quoted


def test_no_em_dash_in_any_tracked_file():
    offenders = []
    unreadable = []
    for rel in tracked_files():
        if rel in WHOLE_FILE_EXEMPT or Path(rel).suffix.lower() in BINARY:
            continue
        path = ROOT / rel
        if not path.is_file():
            # Tracked but not in the worktree: deleted without being staged,
            # or a broken symlink. Either way this guard did not read it, and
            # saying so beats passing over it.
            unreadable.append(f"{rel} (tracked, not a readable file)")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            unreadable.append(f"{rel} (not valid UTF-8, and not a known "
                              f"binary suffix)")
            continue
        if rel in QUOTED_BLOCKS:
            text, _quoted = strip_quoted_block(text, QUOTED_BLOCKS[rel][0])
        if EM_DASH in text:
            offenders.append(f"{rel} ({text.count(EM_DASH)})")

    assert not unreadable, (
        "this guard could not read these tracked files, so it cannot say they "
        "are clean. Add a binary suffix to BINARY if they were never text, or "
        "fix the file: " + ", ".join(sorted(unreadable)))
    assert not offenders, (
        "em dash is banned repo-wide by CLAUDE.md; found in: "
        + ", ".join(sorted(offenders)))


def test_the_whole_file_exemption_is_still_needed():
    """An exemption that stops being true should fail loudly rather than sit
    here forever."""
    for rel, reason in WHOLE_FILE_EXEMPT.items():
        path = ROOT / rel
        assert path.exists(), f"{rel} is exempt but no longer exists"
        assert EM_DASH in path.read_text(encoding="utf-8"), (
            f"{rel} no longer contains an em dash, so its exemption is stale "
            f"and can be dropped. Recorded reason was: {reason}")


def test_the_quoted_block_is_still_where_the_reason_says_it_is():
    """The exemption is the QUOTED REGION, not the file.

    So this fails if the heading moves or the fence goes (the exemption would
    then be aimed at nothing), and if the em dashes are no longer inside the
    quoted block (the exemption would be unnecessary, or worse, covering
    project prose it was never meant to cover).
    """
    for rel, (heading, reason) in QUOTED_BLOCKS.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert heading in text, (
            f"{rel}: the heading naming the quoted block is gone, so this "
            f"exemption no longer points at anything. Reason was: {reason}")
        rest, quoted = strip_quoted_block(text, heading)
        assert quoted, f"{rel}: found the heading but no fenced block under it"
        assert EM_DASH in quoted, (
            f"{rel}: the quoted block no longer contains an em dash, so the "
            f"exemption is stale and can be dropped")
        assert EM_DASH not in rest, (
            f"{rel}: an em dash appears OUTSIDE the quoted NOTICE. That is "
            f"this project's own prose and the exemption does not cover it")
