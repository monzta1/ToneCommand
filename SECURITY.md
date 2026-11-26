# Security

ToneCommand runs on your own computer and talks to gear on your desk. This
page says what it trusts, what it keeps secret and where, and how to report a
problem.

## Reporting a problem

Please report a security problem privately, not in a public issue: use
GitHub's **Report a vulnerability** button on the repository's Security tab
(private vulnerability reporting). Say what you found, the version, and how
to reproduce it if you can. You will get an answer, and a fix ships as a patch
release with credit to you unless you would rather not be named.

## The local server

- ToneCommand's server listens on `127.0.0.1` only. Nothing on your network
  can reach it.
- It answers only to the names `127.0.0.1`, `localhost` and `::1`, so a web
  page that points its own name at your computer (DNS rebinding) is refused.
- A request that changes something and says which page it came from must
  come from ToneCommand's own page, so other sites' pages cannot make changes.
- Every request that changes something (a write to your unit, an update, a
  setup step, a settings change) must also carry **this install's access
  key**. The key is random, made once per install, and kept in
  `access_key.txt` in the install folder (or in `~/.tonecommand` when the
  install folder cannot be written, as for an app in /Applications), readable
  by your user account only. Your browser gets it once, through the link
  ToneCommand opens (or prints) when it starts, and keeps it as a cookie; the
  link then redirects to the plain address, and the server's request log
  shows the key as `<hidden>`. `tonecommand --link` prints the link again for
  another browser. Set `TONECOMMAND_NO_BROWSER=1` to start without opening a
  browser. A script can send the key in an `X-ToneCommand-Key` header.
- Requests over 64 MB are refused before they are read, and a drop of
  captures is limited in count and size before anything is decoded.

**The boundary.** The access key keeps out other user accounts on the same
computer and anything that cannot read your files. A program running as you
can read the key file, as it can read everything else of yours; ToneCommand
is not a sandbox against your own software.

## Your gear

- Writes go to the unit's edit buffer and are read back before they count.
- Storing presets, cab slots and NAM slots is limited to the slots you list
  (`TONECOMMAND_STORE_SLOTS`, `TONECOMMAND_CAB_SLOTS`, `TONECOMMAND_NAM_SLOTS`).
- Firmware and bootloader messages cannot be sent: the device layer refuses
  them by construction.

## Keys and passwords

- **AI service keys** you enter are stored in `ai_settings.json` in the
  install folder, readable by your user account only, and never sent to the
  page. Each key is stored against the address it was entered for and is sent
  only to that address. A key set by hand in `.env` (`PLANNER_API_KEY`) goes
  only to the `PLANNER_BASE_URL` beside it.
- **The ChatGPT connector's password** (for the optional local CLIProxyAPI
  connector) is random, made once per install, and kept in
  `cliproxy_key.txt` (beside the access key), readable by your user account
  only. It authenticates
  ToneCommand to a connector on the same computer and never goes to the page.
- **TONE3000 sign-in tokens** are stored readable by your user account only.

## Updates

The one-click update installs the latest published release only. It moves
the checkout to the annotated release tag GitHub names as latest, only if
that tag is on the main branch on GitHub and the checkout's remote is
GitHub. A checkout already ahead of that release (unreleased work pulled by
hand) is left as it is rather than reported as updated. It then reinstalls
and checks that the new version loads before
restarting. If anything fails, the checkout goes back to the version that was
running. Release tags are not cryptographically signed today; the update
trusts GitHub's HTTPS and the repository's protected main branch.

## Scope

Supported: the latest release. Out of scope: anything that requires a program
already running as your user account, and changes you make to your own
checkout.
