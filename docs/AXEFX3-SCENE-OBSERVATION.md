# Preserving original-scene survey

This explicit component follows the complete read-only observation and bounded
official writer contributions. It is not registered in the ordinary app.
Unlike reading eight names, surveying eight scenes recalls actual scenes and
therefore requires a pinned current target, confirmed external audio mute and
the exact measured official 33.01 declared MK2 connection.

`SceneSurvey.survey()` obtains complete equal current-state observations, then
recalls original scenes 1..8, reads their actual block channels/bypass and
returns to the original scene. Every transition uses one exact typed editor
recall, consumed before transport, followed by repeated complete observations.
Only the current scene and per-block channel/bypass may differ during recall;
names, inventory, full block words, opaque system blocks, modifiers, models,
cabinet state and grid must remain unchanged. No assignment is rewritten.
The final original-scene observation must equal the initial observation.

No missing/failed map is inferred from names or another scene. Readback may
settle, but the recall is never retried. Unknown outcomes latch the connection
without automatic rollback, preset reload or original-scene restore. Keep
external audio muted and inspect before reconnecting after a failure.

This adds no model, level, bypass/channel assignment, controller, route, NAM or
Store write. Direct raw scene messages remain refused at the final output
boundary. The existing typed scalar experiment remains separate. No AI host,
UI route, production registration or physical MK1 qualification is implied.
Eight-scene scalar compilation/execution and normal REVIEW/CONFIRM/SEND wiring
are later pieces. Synthetic tests and native acceptance remain distinct.
