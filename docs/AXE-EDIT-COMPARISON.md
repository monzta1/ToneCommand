# Axe-Edit information dialogs during developer comparison

This is a Windows developer measurement aid, not TC's NAM installer. Native
NAM download, preview, backup, install and full-memory readback do not require
Axe-Edit. Do not add an editor dependency to those application workflows.

## Use

With the existing editor process ID, first inspect without clicking:

```powershell
python -m tools.axe_edit_dialogs --pid 504
```

The PID is an example. To acknowledge only the measured Manage NAM information
popup, explicitly opt in:

```powershell
python -m tools.axe_edit_dialogs --pid 504 --ack-known-information
```

The helper verifies the executable path and complete modal content, including
the unique enabled OK button. The initial inspection is repeated before
action. After focusing the modal, its foreground identity and content are
checked again. One click uses the current control, not a stored coordinate or
Enter key. Closure is verified with bounded polling. A comparison must not
continue after a blocked result or nonzero exit.

Default inspection reports `known-information`, without accepting it. An
explicit acknowledgement that succeeds reports `clear` and `acknowledged:
true`. No visible UIA modal also reports `clear` but `acknowledged: false`.
That only describes the inspected modal controls; it is not a test of MIDI,
unexposed custom overlays, routing, selected captures or hardware parameters.

Unknown content, additional buttons/windows, disabled OK, a foreground mismatch
or a changed dialog stops execution. Save, overwrite, delete, firmware, account
and permission dialogs are never implicitly accepted. A dialog that remains
open after the single click is not repeatedly clicked. Screenshots and status
are written only under ignored `backups/axe-edit-dialogs`; unknown message
bodies are not copied into status logs or public source.

`pywinauto` is an optional dependency in the developer environment. The helper
never launches or closes the editor, opens MIDI, presses Save, changes presets
or installs NAM data. For any subsequent hardware comparison, release TC's
MIDI connection first and use only the agreed test presets and NAM slots.

## Integration in a measurement harness

```python
from tools.axe_edit_dialogs import EditorDialogs, handle_information

editor = EditorDialogs(existing_pid)
result = handle_information(editor.read, editor.acknowledge, permit=True)
# Only continue if this returns successfully; never swallow DialogBlocked.
```

Run the guard before interacting with the editor and after any action that may
open a modal. Only the complete measured Manage NAM message is allowlisted.
Adding another known informational message requires independent observation
and negative tests for nearby destructive confirmations. Never replace this
guard with "click the first OK" or an unbounded dialog-dismissal loop.

## Local verification, 2026-10-09

The actual running Axe-Edit process exposed a Manage NAM Window with ContentText
and CommandButton_0. The UIA message has a duplicated `to`; both this measured
variant and the displayed spelling are matched exactly after whitespace
normalization. UIA Invoke did not close the modal and the first attempt stopped.
The foreground-checked button click subsequently closed the known popup and
the helper verified that no visible modal remained. No preset, NAM memory,
global setting or Save action was performed. Screenshots and JSON remain local.

This proves handling of this information popup, not a NAM capture selector.
The earlier composite tool rejection occurred before execution and is separate
from an editor popup. It is not resolved by this result and must not be bypassed.
