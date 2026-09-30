# Protocol contributions

Original findings from this project's hardware verification (FM9 firmware
11.00 and 12.00), offered back to the community projects credited in
[CREDITS.md](CREDITS.md). The living protocol record, with evidence per
claim, is [PROTOCOL.md](PROTOCOL.md).

1. **FM9 grid insert requires a cell-select first.** The insert frame
   (fn 0x01 sub 0x32) alone lands the block on the device's internal
   cursor, not the frame's target cell. Sending the cell-select
   (sub 0x30, cell index as a raw uint32 in 5 septets) immediately before
   makes placement honor the target. Upstream documents the FM9 as not
   needing the select; that conclusion came from status-dump verification,
   which can confirm a block exists but not where it landed. Grid-read
   verification exposes the difference.
2. **Grid-read effect IDs alias mod 128.** The sub 0x2E grid bitstream
   stores the block id in 8 bits as (id << 1), so effect ids >= 128 wrap:
   FX Send (182) reads as 54, FX Return (186) reads as 58. Disambiguate
   against the fn 0x13 status dump.
3. **FM9 modifier source ordinal 11 = Pedal 2 (EXP/SW TIP),** confirmed
   physically. Upstream marks the FM9 source enum as uncaptured with an
   explicit warning against assuming the FM3's values; at least around the
   pedal entries, the FM3 ordering holds on the FM9.
4. **Documented dead ends** so nobody re-burns time on them: the sub 09 00
   GET always returns a zeroed value field on fw 11.00 (use the fn 0x1F
   bulk read instead); the sub 0x1F display-name query returns "NONE" for
   modifier source enums, and for the amp block it returns the roster's
   FIRST entry regardless of the actual amp type - before and after
   writes, through seconds of settle (proven on fw 12.00 by
   @bschmalz81401, reproduced on fw 11.00; this project's earlier "fresh
   for amp" claim was wrong). Never verify a type through it; read the
   wire value and map through the roster. Live modulation (a moving
   pedal) is invisible to every known read, so pedal bindings must be
   verified physically.
5. **Cable drawing hardware-validated.** The community's 6-row cable
   encoding formula (fn 0x01 sub 0x35), previously byte-derived from
   captures but unverified as a live write, draws correct cables on FM9
   firmware 11.00: all masks confirmed by grid read-back. Also verified:
   placing an already-placed block at a new cell is ignored (a "move" is
   clear-then-insert, and clearing a cell destroys its cables).
6. **Shunt-replacement insertion.** Placing a block onto an existing shunt
   cell inherits the shunt's cables, which makes it possible to add effects
   into a preset's signal chain without touching the only partially decoded
   cable-drawing encoding at all.
7. **Same-row cable draws on row 2 use their own encoding.** The general
   6-row formula silently draws nothing for a row-2-to-row-2 connection.
   Probed on hardware (fw 11.00): odd source columns need dest_sign 0 with
   b23 3, even columns dest_sign 1 with b23 1. The general formula's
   prediction for those byte values collides with a different geometry, so
   the same bytes mean different things than it assumes. Row 5 same-row
   draws match the general formula. Also observed: a 2-row diagonal draw
   does not register at all, and re-sending an identical draw does NOT
   remove the cable (removal is op 0x02, item 12).
8. **Writes are asynchronous; unsettled reads lie plausibly.** A read
   issued immediately after a write returns the pre-write state with no
   error indication. The bundled simulator now models this (an 80ms settle
   window) and additionally tracks "undecoded territory": operations no
   hardware session has verified are reported by name rather than
   silently simulated.
9. **Empty preset slots identify themselves, and leave a ghost.** The FM9
   writes its own marker, `<EMPTY>`, into an unused slot's name field - so
   detecting a free slot needs no heuristic. Clearing a slot overwrites
   only the FIRST 8 BYTES of the 32-byte name field and leaves the rest of
   the previous name in flash, so name fields must be cut at the first NUL
   rather than right-stripped. Right-stripping yields the marker glued to
   the tail of a preset that no longer exists (`'<EMPTY>\0 Phat Time'`).
   Verified across all 512 slots on fw 12.00.
10. **fn 0x0D reads any slot by number, out of flash, without loading it.**
    Passing a preset number instead of the "current" sentinel answers from
    storage and leaves the loaded preset and the edit buffer untouched, with
    the requested number echoed back. A 512-slot sweep was byte-identical to
    a select-and-read sweep of the same unit and took 4.7s instead of ~4.5
    minutes, with the front panel never moving. Confirmed on fw 11.00 and
    12.00. Out-of-range numbers are ANSWERED rather than refused - preset
    512 returns a blank name field - and a blank is not the `<EMPTY>`
    marker, so unguarded readers call a nonexistent slot occupied.
11. **A preset can be built from nothing.** An empty slot has NO grid cells
    at all and no Input or Output blocks - its status dump carries only the
    ever-present ids 200 and 201 - so there is nothing to splice into and no
    cable to inherit. Placing blocks into that blank grid works, Input and
    Output included, each arriving uncabled. Same-row cable draws on row 3
    then work with the general 6-row formula (previously only rows 4 and 5
    were confirmed; row 2 needs its own encoding, item 7). Verified on
    fw 12.00 by building Input -> amp -> cab -> Output across columns 1-4
    and confirming the result audible by ear.
12. **Cable removal is the draw message with op 0x02.** The routing message
    (sub 0x35) carries an op byte; 0x01 connects and 0x02 disconnects, with
    the identical geometry encoding. Verified on fw 12.00: it clears the
    destination mask, survives repeated remove/redraw cycles, is idempotent
    rather than a toggle, and is SELECTIVE - on a cell fed by two sources it
    clears only the named source bit. Prior belief, ours included, was that
    removal was a different and unknown message.

## BOSS IR-2 (decoded 2026-09-29)

A second device family, decoded here and written down because no
third-party MIDI specification for this pedal appears to be published.
Verified on hardware; nothing below is inferred from another Roland
product.

13. **The IR-2 speaks Roland addressed SysEx**, model ID `01 05 09`,
    device `0x10`, with RQ1 (`0x11`) to read and DT1 (`0x12`) for data,
    a four-byte address, a four-byte size and the standard Roland
    checksum. Its Universal Identity Reply is
    `F0 7E 10 06 02 41 09 05 00 00 00 00 00 00 F7`, so the model ID is
    NOT the identity reply's family bytes in the order they appear
    there, which is the obvious wrong guess.
14. **It announces its own panel.** Moving any knob emits an unsolicited
    DT1 at `20 00 00 0N` roughly every 40 ms, and a footswitch press
    emits three frames: the switch event at `7F 00 01 04`, the whole
    seven-byte patch block, and the active-patch flag at `00 00 00 00`
    toggling between `00` and `01`. An RQ1 read afterwards returns
    exactly what was pushed, byte for byte, so reads and pushes agree
    and the device has a genuine read path rather than local tracking.
15. **Over-requesting a size returns the block's real length**, which
    makes the address map discoverable without ever writing: `00 00 00 00`
    is 1 byte, `10 00 00 00` is 12, `20 00 00 00` is 7 and
    `30 00 00 00` is 32.
16. **Out-of-range writes clamp silently rather than failing.** Writing
    `0x0B` to the AMP parameter (range 0 to 10) reads back as `0x0A`.
    A naive write-then-read-back would report that as a successful
    write of `0x0B`, so ranges must be checked before sending, not
    after.
17. **Documented dead end:** the identity reply's software revision
    field is all zeros on this unit, so there is no firmware version to
    read there. Report none rather than inventing one.

The pedal's own parameter table, including names and ranges, ships as
readable JavaScript inside BOSS's IR-2 IR Loader
(`Contents/Resources/html/js/config/address_map.js`). Where that table
and the hardware overlapped they agreed, including the AMP range, which
had already been found by watching writes clamp.

## Grounding data

The planner grounds Fractal's model names in the real-world gear they
model, so "give me a Klon into a JCM800 with a greenback 4x12" resolves
to actual ordinals instead of guesses:

| Domain | Coverage | Source |
|---|---|---|
| Amp models | 331 / 331 | Yek's Amp Guide (community PDF, facts only) |
| Drive models | 86 / 86 | Yek's Drive Guide + Fractal wiki Drive block page |
| Cab IRs | 2,235 / 2,237 | Fractal wiki Cab models page (via @bschmalz81401) |
| DynaCabs | 45 / 45 | same |

All sidecars are facts-only (no prose reproduced), carry the Fractal
name they were built against, and fail loudly if a catalog update
renumbers the rosters. Unknowns stay unknown: nothing is invented.
