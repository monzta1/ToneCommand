# Preserving preset observations: receive-only foundation

This independent next slice after #296/#297 extracts the observation layer,
not the larger fork's live reader or executor. It is not registered in the app.
Existing connection/output boundaries, routes, UI, capabilities and writers are
unchanged. The source has no transport, device, provider or model-map import.

## Included

`observed_words.assemble` consumes one isolated, finite 0x74/75/76 broadcast.
It checks product, checksum, target ID, header/body/end layout, declared word
count, uint16 packing and bounded packet sizes/counts. Truncated, extra, wrong
or unrelated packets fail rather than returning partial/default-filled words.
The existing codecs and third-party-spec attribution stay in `fm9.protocol`.
Only the observed zero section/reserved body layout is admitted; other layouts
refuse rather than being guessed or silently skipped.
No outgoing frame or query is constructed or sent by this component.

`preset_observation.observe` requires the complete *observed* surface: raw
identity, declared chassis capacity, current target, eight scene names, block
inventory, occupied grid/cable masks, counted broadcasts for every block
including opaque system blocks 200/201, and all 32 ordered modifier records.
Unknown effect instances and all uint16 values, including 65535, remain opaque.
Unused modifiers retain every word, even residual assignments or unknown curves.
Missing names, blocks, grid cells or broadcasts are not filled with defaults.

Only status/grid presentation order is canonicalized. Parameter order, modifier
order, names, channels, bypass states, shunts and masks remain unchanged. The
returned immutable canonical observation exposes a detached copy and digest,
not a write permit, approval ticket, `.syx` backup or restore image.

`capture` takes an explicitly injected fresh-read callback and requires two
consecutive equal complete observations. It may retry complete but unequal
readings within a strict bound. Bad data, reader errors or identity/target
drift stop immediately; there is no automatic recovery, navigation or write.

## Boundaries and remaining hardware work

Structural count checks are not qualification of a model's parameter layout.
The host must independently qualify identity, codecs, exact lengths and write
rights later. The display label and declared chassis cannot grant permission.
Current-scene channel/bypass status and eight names are **not** eight observed
scene maps. Disconnected or dangling routing is retained, not repaired or
certified as audible. This is not every undocumented byte of device memory.

The future reader must supply isolated fresh bursts, check the target before
and after assembling each observation, and use an independently approved
read-only transport. Injection and validated data cannot prove that provenance.
The ordinary app still refuses editor grid/bulk requests at its output gate.
This PR does not enable those requests, call a MIDI factory or touch the unit.

Live read integration and native comparison with Axe-Edit, exact official
33.01 writer qualification, muted scene survey, delta execution and GUI wiring
remain separate contributions/tests. Physical Mark I acceptance is separate.
All new fixtures are synthetic; no factory/user preset, IR, NAM or account
payload is redistributed. Existing local hardware evidence is not relabelled
as native acceptance of this upstream extraction. No hearing/tone-match claim.
