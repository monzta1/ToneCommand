# Explicit Codex CLI proposals

## Current review status: runner withdrawn

Do not merge or enable this backend as a runnable planner. The previous
`exec --sandbox read-only` runner was removed: read-only execution can still
use tools and inherits user configuration. Saved backend/model preferences
remain readable, but requests fail explicitly before discovery, account reads,
process creation or output allocation. No automatic provider fallback occurs.
The settings picker reports this backend unavailable even if Codex is installed.

No Codex subprocess exists to outlive a timeout, produce unbounded output or
ignore STOP. This removes that exposure; it does not claim an implemented
process-tree/cancellation/output-limiting transport. Pre-start STOP is tested.

A replacement requires a documented and independently tested all-tools-off
contract (including shell, MCP and configuration isolation), process-tree
termination, cancellable calls and byte limits for both pipes and the final
file. Until then, choose another existing backend explicitly. Existing API
backends and device capabilities are unchanged. The historical design below
is reference only, not current availability or security evidence.

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
