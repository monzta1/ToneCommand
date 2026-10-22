# Pull request note: new design from the request screen

Include this UI change in the planned upstream pull request, alongside the
separately documented Axe-Fx III integration. This file is a local PR draft,
not a claim that a pull request has been published or merged.

## User-facing change

- Add an always-visible **NEW DESIGN** button to the request screen.
- Clear the conversation, typed draft, agreed name/scenes and current plan.
- Confirm before discarding existing work; cancellation preserves everything.
- Disarm sending, clear review acknowledgement and focus an empty input.
- Route existing CLEAR and post-send NEW REQUEST buttons through the same reset.
- Refuse resets during AI, source-reading or hardware-send work, preventing
  an old asynchronous response from entering a new design.
- Do not clear or reload the connected preset, select a scene or send MIDI.
  Already applied edits remain in the device's edit buffer.

The owner's audio-enabled interface also clears old measurement context and
retry metadata while retaining the selected link/file for a fresh analysis.
That owner-specific audio workflow is not implicitly enabled in upstream.

## Verification

Run the shared reset behavior tests against the shipped UI source, including
confirmation cancellation, busy states, an armed unsent plan and no network
or device writes. Run the existing UI syntax and mandatory capability gates.
Do not publish private settings, captures, cab exports or evidence files.

Local verification on 2026-10-06: **87 Python tests passed**, including the
mandatory device/capability/UI gates and shipped-script syntax checks.
Five Node reset tests passed against each interface. Real installed Chrome
passed confirmation cancellation, accepted reset, empty-input focus and
button visibility at the main UI's supported desktop widths (1280/1180px)
for both source versions, against a dedicated SIM server with all writes
blocked. The owner's existing audio/UI behavior suite passed **60 tests**.
No paid AI calls, MIDI writes, publication or merge were performed.
