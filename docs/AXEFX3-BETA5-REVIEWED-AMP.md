# Beta5 reviewed Amp experiment

Separate opt-in developer experiment, not general Beta5 preset building or
an extension of the older firmware writer's approval.

## Scope

- Exact MK2 build `33.00-beta5.20261026`, full-response SHA-256
  `15e9277d25e2180599d6d8a9d1fda73373ee592cdc0ce8682a1f7c007b67a616`.
- Existing Amp1/A, model0, 59 Bassguy Bright. No model, block, channel,
  scene, bypass, level, controller, Store or NAM/global writes.
- One Gain or Mid value, 0.1..8.0 in tenths, at most one displayed unit
  from the fresh value. Zero and arbitrary precision refuse.
- Existing connection/target, immutable digest, single-use native review,
  expiry, explicit mute/target confirmations and deliberate SEND required.
  No automatic retry, rollback, Undo or Store.

Default stays read-only. Explicit developer selection uses
`TONECOMMAND_AXEFX3_REVIEWED_AMP_BETA5=1`; leave
`TONECOMMAND_AXEFX3_REVIEWED_AMP` unset. Both flags together refuse connection.
The older flag retains the older writer and its unchanged identity pin.
Neither mode enables a full-workspace firmware profile, AI whole-rig build,
names or other parameter families. Modes cannot share an armed review.
MK1/Turbo and unknown responses refuse. No model is silently loaded.

The manual controls use the existing shared Plan/Review/Confirm/Send stages.
A retained ordinary-plan revision can still conservatively block preparation;
the host lifecycle limitation remains in
[the backlog](AFX3-COMPLETION-BACKLOG.md).

## Native/editor evidence, 28 October 2026

Only isolated, bypassed327/scene1 with no Input, Output or cables was used.
Six editor boundary literals, Gain0.1/8.0/4.4 and Mid0.1/8.0/5.0, were
captured and independently replayed once each. Settled/repeated full-state
reads and independent displays passed. All unrelated state stayed exact and
the final full baseline was restored.

The registered prepare/review/confirm/send routes used the actual new
component for Gain4.4->4.6 and a fresh separate review4.6->4.4, then
Mid5.0->5.6 and a fresh separate review5.6->5.0. Exactly four SETs, no
retries. Preparation/review/confirmation alone sent none. Fresh Axe-Edit
instances showed changed Gain, restored Gain and changed Mid independently.
After restoration and the boundary batch, a fresh editor showed Gain4.4,
Mid5.0, model0, bypass, -12dB and original remaining controls. A final native
full-state comparison stayed exact.

Each native test's final transport additionally admitted only the exact
editor-captured SET bytes being tested, plus GETs. Captures, complete state,
preset names and screenshots stay private. Shared guard and storage allowlists
were unchanged. The fixture was not saved or auditioned.

These are native API tests, not actual native browser SEND, audible quality,
all336 model voicings or complete Beta5 compatibility. Final software, CI and
installation acceptance are recorded separately. External mute and conservative
levels are not a physical limiter.

## Separate upstream-port acceptance, 30 October 2026

The exact PR294 runtime source85d86beb2f7db4f1430bc2f7aa313c30e8a335ab
subsequently passed its own registered native prepare/review/confirm/send
transactions: Gain5.0->4.6->5.0 and Mid5.0->5.6->5.0. Each SET had a new
review and a final output restriction to one exact captured literal plus
GETs. Actual upstream module paths/hashes were recorded; canonical full-state
readers ran in separate processes, not in the upstream Python namespace.

Two equal full-state observations followed each transaction. Only its target
Amp A word changed, and the complete baseline was restored. Independent
fresh Axe-Edit1.15.02 comparisons covered the baseline, changed Gain, restored
Gain with changed Mid, and final restored controls. The owner had freshly
confirmed power and external mute.327 remained disconnected and bypassed at
-12dB; no Store, NAM/IR/global/firmware write or reference326/328 change.

An initial test-harness request correctly refused the default nonlocal Host
after constructor GETs only. The harness was corrected to127.0.0.1; no security
gate was relaxed. This exact upstream API/editor evidence is separate from
the earlier77e2ded fork proof. No native browser SEND or broader approval.
