# Explicit live Axe-Fx III observations

This focused follow-up depends on the receive/observation foundation in #298.
It is not registered in the app and grants no new rights to the normal adapter.
`LiveReader` is a separate read-only acceptance component. Its final output gate
accepts existing basic GETs, one literal editor grid GET and whole-block GETs
for IDs 1..207. It never sends SET, scene/preset navigation, memory installation,
NAM selection, Store or controller writes, even through direct `outp.send()`.

Physical III adapters acquire one shared nonblocking OS lease before opening
MIDI. A second reader, even from another TC process/checkout, refuses before
port open. The handoff is explicit: close the old owner normally, then open
the new one. Both port closes must succeed before releasing the lease; uncertain
close failures retain it until process exit. No forced closure or takeover.
Injected test ports are trusted test/caller-owned IO, not a second physical
open. External programs do not cooperate with TC's lock: Axe-Edit must still
close normally before inspection, and the reader closes before editor comparison.

`capture()` obtains two consecutive equal full observations. Each fresh pass
reads the full identity, declared chassis and current target; status and full
eight-bit grid; every counted status block including opaque system 200/201;
all 32 modifier records and eight scene names. It rechecks identity, target,
status and grid before validation. Invalid, interleaved, truncated, excessive or
timed-out block bursts fail without returning cached/partial/default values.
Deadlines include stale draining and are checked inside every receive iteration,
including non-SysEx traffic. Basic identity/status reads have the same protection.
Each broadcast is capped at4096 received messages,1024 buffered frames,776 bytes
per frame and65536 total buffered bytes. Sizes are checked before copying and
assembly, not afterwards. No timing-only test is substituted for these bounds.
Target drift stops rather than accepting a different preset. Complete unequal
passes may settle within a bounded read count; no write or recovery is retried.

Bulk layout and grid decoding retain the attribution in `fm9.protocol` and
`THIRD_PARTY_NOTICES.md`. Full eight-bit IDs preserve NAM206 rather than aliasing
it to Chorus78. Unknown data and custom modifier words stay opaque. Declared
broadcast lengths establish structural completeness, not model codec rights.

The firmware string remains a raw display label unless the independent #296
label contribution is integrated. No label promotes writing. The chassis is
declared by the caller, not detected by this reader. Physical MK1 acceptance
remains separate. Reading eight names is not recalling/inspecting eight scene
channel maps. This is not a `.syx` backup, restore operation, acoustic check or
proof of every undocumented device byte. The protocol has no request nonce:
fresh drains, isolated request bursts and repeated target checks cannot prove
that a user never switched away and back between polls. Concurrent control
must remain stopped during inspection.

The pure synthetic tests are not native acceptance. Exact-source native
read-only comparison and an independent Axe-Edit comparison are recorded
separately when performed. Official firmware writing, muted scene survey,
existing-preset execution and REVIEW/CONFIRM/SEND remain subsequent pieces.
