# Axe-Fx III read only review

## Read-only follow-up, 28 October 2026

On the owner's Mark II with the exact Beta5 build20261026, all1024 native
name reads were compared with an independent Axe-Edit III1.15.02 text export
from Tools > Export As Text > Preset List. Every requested address replied
with its correct number. There were1022 exact name matches, including511 of
the512 upper-half names. Two exported names omitted an initial space retained
by the native reader, one in each half. These differences remain visible;
do not call this1024 byte-exact name matches or silently trim stored names.
All other name characters agreed. This does not verify MK1/Turbo hardware.

The name scan sent only strict read forms and preserved its complete basic
status snapshot. Separate double full-grid/bulk/modifier/name reads before
and after it also matched. During editor preparation, the disposable327
unsaved Amp/Pitch fixture was reloaded; its full prior observation was kept.
The comparison itself did not select/store presets. No Save, NAM/IR install,
global change or write to326/328 was performed by these tools.

The shared read-only adapter now labels previously observed full firmware
responses by their exact existing fingerprints. An unknown response still
falls back to its raw fields, including97.00; it is not assumed to be a known
build. The read-only final output guard and all write capabilities are unchanged.
Recognizing Beta5 does not make it a general write profile or identify chassis.

The optional offline checker preserves spaces and reports counts/indices only:

```text
python -m tools.axefx3_name_list --editor-export editor.txt --tc-export tc.json --chassis mk2
```

The TC file contains a complete list of `{number, name}` entries, optionally
under a `slots` key, for the declared MK1/512 or MK2/Turbo/1024 range. Invalid,
duplicate or incomplete inputs fail visibly. Raw differences return exit1,
even if they contain only outer spaces. The checker opens no MIDI connection
and grants no hardware permission. Keep name-list inputs private; share only
the resulting counts/slot indices unless you intentionally want names public.

## Full-fork path mapping, 28 October 2026

The upstream read-only implementation maps to `readonly_adapter.py` and
`readonly_protocol.py` under `devices/axefx3` in this Unofficial fork. The
shared Devices selector uses that boundary. The existing `adapter.py` and
`protocol.py` remain the separate guarded workspace. Do not substitute those
in this slice's tests or infer write permission from read-only acceptance.

The remainder records the original slice's historical scope and evidence;
the dated follow-up above supersedes its upper-half/known-label status.

This is the basic reading slice of [the larger contribution](https://github.com/monzta1/ToneCommand/pull/270).
It lets the existing Devices selector open an Axe-Fx III without enabling
preset writing, NAM installation or account workflows. The full working fork
and the separate MK1 evaluation package do not change when this slice changes.

## What it reads

The adapter queries firmware major/minor, the current preset and scene,
stored preset names in the declared hardware range, eight scene names and block
bypass/channel status. Names are read by number without selecting a preset
or scene. The screen shows status chips, not an inferred signal route.
Unknown effect IDs remain visible by number, rather than borrowing an FM9
effect type or NAM map. No amp, cab or parameter values are inferred.

Firmware major/minor is not an exact beta build identifier or proof that any
write works. MK1 and MK2 are not detected or distinguished by these reads.
In **Devices > Axe-Fx III**, declare Mark I (512 presets), Mark II (1024) or
Turbo (1024). The default is conservatively Mark I. The box is hidden unless
a III is available, active or selected.
Opening Devices or changing this box's visibility does not connect anything.
The FM3 settings card is likewise hidden when irrelevant. A generic
"Set up a MIDI device" action can reveal its configuration intentionally,
since a first-time FM3 behind a MIDI interface cannot identify itself over USB.
The hardware declaration is local to this server session and is not an
automatic hardware identification.
Only stored-name requests expand: wire slots 0..511 for Mark I, 0..1023 for
Mark II/Turbo. Select the actual chassis, not MK2 as a workaround on a Mark I.
The write boundary is identical for all choices and does not inspect NAM or
User Cab memory. No controller, NAM or write compatibility is inferred.

## Start and compare

1. Install the project normally with Python 3.12 and `pip install -e ".[dev]"`.
2. Close Axe-Edit and any other application holding the unit's MIDI port.
   Keep monitoring muted when changing presets manually during the comparison.
3. Start ToneCommand normally. Open Devices and declare your connected III's
   hardware type. The device picker also connects using the current declaration.
   A Mark II/Turbo loaded above slot 511 needs its type chosen before connection;
   the conservative Mark I default deliberately refuses that out-of-range reply.
   Discovery enumerates names only; it opens no MIDI ports until selection.
4. Check preset, scene and block states against the unit. Scene and preset
   navigation from this UI is disabled in this slice. Make any desired
   changes on the unit, then refresh the reading.
5. Switch TC back to FM9 or stop its console normally before opening Axe-Edit.
   Record exact unit firmware/build, editor version and MK1/MK2 chassis, then
   compare names and bypass/channel status. Do not save or install anything
   for this test. Close Axe-Edit before reconnecting TC.

An occupied port, missing reply, wrong product byte, invalid checksum or a
preset/scene transition during the snapshot must not be reported as a passing
read. A missing individual scene name stays unknown. A different device's
response is ignored. Unplug/reconnect uses the existing reconnect control.
Changing the declared type on an already connected III sends no MIDI message;
it invalidates cached names. Use RESCAN to read the declared range. Names from
another device, adapter connection or chassis declaration are not reused.
Neither the names scan nor the chassis choice selects or saves a preset.

## Higher preset name acceptance

On a real Mark II, read all names with the Mark II declaration, then compare
the upper half against Axe-Edit with TC disconnected first. Record exact
firmware/build and editor version, and specifically compare wire slots 512
and 1023. Axe-Fx III labels use these same zero-based numbers; the FM9 keeps
its own one-based display convention. Keep monitoring
muted for any manual preset/scene change. Close Axe-Edit before reconnecting TC.
Confirm the selected preset and scene remain unchanged during TC's scan.

On 2026-10-23, the read-only adapter read all 1024 names on a Mark II and
repeated all 512 upper names without changing the current preset, scene or
block status. Axe-Edit III 1.15.01 independently displayed matching names at
512 and 1023, and confirmed zero-based numbering. Its status identified the
unit as Mark II / FW 33.00 beta. This adapter still reports the raw version
fields as 97.00; exact beta identification remains a separate investigation.
The full upper-half name-by-name editor comparison is not yet complete.
Do not send above-511 requests to a Mark I to investigate its
unknown response. Missing names remain unknown; a timeout is not an empty slot.

## Read boundary

The final output wrapper accepts only exact product 0x10 checksummed read
forms for functions 08, 0A, 0B, 0C, 0D, 0E and 13. Scene 0C accepts only its
query sentinel. Bypass and channel accept only queries, never values. The
parameter/editor function 01, bulk/memory transfers, CC/PC, clock, notes,
firmware and storage commands are refused before output. A getter is never
implemented as a zero-value setter. The FM9 send guard stays unchanged.

All core write methods decline explicitly. Preset planning for this device stops
before calling the AI. Capability flags remain false for writes, topology,
modifiers, captures, file installation, renaming and Store. No new HTTP
endpoint, account, dependency, write-slot allowlist or FM9 protocol switch is added.

## Review and remaining tests

Offline tests cover strict output forms, malformed and wrong-product replies,
timeout/close behavior, request correlation, scene/preset coherence, adapter
conformance, selection/state endpoints and write refusals. The existing full
suite and mandatory safety/capability checks accompany the draft, with any
platform-specific failures disclosed in its description.
The Mark II checks above cover names and current-state preservation, not
new write acceptance. External MK1 testing and a complete upper-half editor
comparison remain pending.

Review MIDI partial-open cleanup separately; it is the first small PR and is
recommended before live connection testing. The two PRs both target upstream
main and carry no overlapping implementation commits. Later slices can extend
this adapter with separately reviewed preset writes, NAM and account flows.
