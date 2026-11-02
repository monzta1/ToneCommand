# Explicit Codex CLI proposals

Optional shared planner backend, independent of the Axe-Fx III adapter.
Select `codex` in AI settings only if an installed Codex CLI is already signed
in. This does not install software, start a browser login, change accounts,
forward API keys, add a hosted subscription or select a different provider.
An absent binary or failed request is reported without provider fallback.
Automatic backend order remains unchanged and never includes Codex.

An explicit absolute `TONECOMMAND_CODEX_CLI` path is authoritative. Otherwise
resolution uses PATH, then existing standard Windows installs or a matching
architecture in a versioned VS Code/Insiders extension. Invalid explicit paths
never fall through. `CODEX_CLI_MODEL` optionally overrides the local configured
default. No model list or model availability is invented.

The runner requests an ephemeral, read-only CLI execution with the proposal
on stdin, using a neutral temporary working directory. It reads the final
UTF-8 output file rather than treating progress stdout as a plan, and removes
its own temporary file on success or failure. Process environment is allowlisted;
unrelated API/cloud credentials do not travel. CLI diagnostics are not echoed
to the browser. JSON parsing and the normal caller validation still apply.

Read-only CLI execution is not a device or audio safety boundary. The returned
proposal has no MIDI permission; normal TC review, consent, capability gates
and independent execution checks remain mandatory. No device/Store route or
firmware qualification is added by this backend.

Flags follow the [official CLI command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli).
Synthetic provider/environment/resolver/settings tests make no AI calls and
use no account. Any live selected-account GUI result is separate evidence.
