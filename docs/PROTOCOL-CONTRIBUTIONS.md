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
