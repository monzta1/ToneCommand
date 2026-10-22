from dataclasses import replace
from unittest.mock import Mock

import pytest

from tools import axe_edit_dialogs as dialogs


def known():
    return dialogs.Dialog(123, "Manage NAM", (("ContentText", dialogs.NAM_INFORMATION_UIA),),
                          (("CommandButton_0", "OK", True),))


@pytest.mark.parametrize("body", [dialogs.NAM_INFORMATION, dialogs.NAM_INFORMATION_UIA,
                                dialogs.NAM_INFORMATION_UIA.replace(". ", ".\n\n")])
def test_measured_information_text_variants(body):
    assert dialogs.classify(replace(known(), texts=(("ContentText", body),))) == "nam-manager-information"


@pytest.mark.parametrize("change", [
    {"title": "Save NAM"}, {"title": "Manage NAM - overwrite"},
    {"texts": (("ContentText", "Overwrite slot 001?"),)},
    {"texts": (("ContentText", dialogs.NAM_INFORMATION + " Overwrite?"),)},
    {"texts": (("ContentText", dialogs.NAM_INFORMATION), ("extra", "Save changes?"))},
    {"texts": (("OtherText", dialogs.NAM_INFORMATION),)},
    {"buttons": (("CommandButton_0", "Save", True),)},
    {"buttons": (("CommandButton_0", "OK", False),)},
    {"buttons": (("OtherButton", "OK", True),)},
    {"buttons": (("CommandButton_0", "OK", True), ("CommandButton_1", "Cancel", True))},
])
def test_unknown_save_overwrite_disabled_or_ambiguous_dialogs_are_never_allowed(change):
    dialog = replace(known(), **change)
    assert dialogs.classify(dialog) == "unknown"
    action = Mock()
    with pytest.raises(dialogs.DialogBlocked):
        dialogs.handle_information(lambda: [dialog], action, permit=True)
    action.assert_not_called()


def test_no_dialog_does_nothing():
    action = Mock()
    assert dialogs.handle_information(lambda: [], action, permit=True)["status"] == "clear"
    action.assert_not_called()


def test_default_is_inspection_only():
    action = Mock()
    assert dialogs.handle_information(lambda: [known()], action) == {
        "status": "known-information", "acknowledged": False}
    action.assert_not_called()


def test_known_info_acknowledged_once_and_verified_closed():
    read = Mock(side_effect=[[known()], [known()], []])
    action = Mock()
    assert dialogs.handle_information(read, action, permit=True)["acknowledged"] is True
    action.assert_called_once_with(known())


def test_multiple_dialogs_stop_before_any_acknowledgement():
    action = Mock()
    with pytest.raises(dialogs.DialogBlocked, match="multiple"):
        dialogs.handle_information(lambda: [known(), known()], action, permit=True)
    action.assert_not_called()


def test_dialog_changed_between_inspection_and_action_stops():
    read = Mock(side_effect=[[known()], [replace(known(), handle=456)]])
    action = Mock()
    with pytest.raises(dialogs.DialogBlocked, match="changed"):
        dialogs.handle_information(read, action, permit=True)
    action.assert_not_called()


def test_unknown_dialog_after_acknowledgement_is_not_accepted():
    read = Mock(side_effect=[[known()], [known()], [replace(known(), title="Save")]])
    action = Mock()
    with pytest.raises(dialogs.DialogBlocked, match="different"):
        dialogs.handle_information(read, action, permit=True)
    action.assert_called_once_with(known())


def test_no_repeat_click_when_dialog_does_not_close():
    action = Mock()
    with pytest.raises(dialogs.DialogBlocked, match="did not close"):
        dialogs.handle_information(lambda: [known()], action, permit=True, timeout=0)
    action.assert_called_once_with(known())


def test_transient_close_is_waited_for_without_repeated_acknowledgement():
    read = Mock(side_effect=[[known()], [known()], [known()], []])
    pause = Mock()
    action = Mock()
    result = dialogs.handle_information(read, action, permit=True, pause=pause)
    assert result["status"] == "clear"
    pause.assert_called_once_with(0.1)
    action.assert_called_once()


def test_last_moment_content_change_prevents_invoke():
    editor = object.__new__(dialogs.EditorDialogs)
    window = Mock()
    editor._windows = Mock(return_value=[window])
    editor._snapshot = Mock(return_value=replace(known(), title="Overwrite"))
    with pytest.raises(dialogs.DialogBlocked, match="Last-moment"):
        editor.acknowledge(known())
    window.descendants.assert_not_called()


@pytest.mark.parametrize("foreground,current", [
    (999, (known(),)), (123, (replace(known(), title="Save"),)),
])
def test_foreground_or_content_change_after_focus_prevents_click(foreground, current):
    editor = object.__new__(dialogs.EditorDialogs)
    window = Mock()
    editor._windows = Mock(return_value=[window])
    editor._snapshot = Mock(return_value=known())
    editor._foreground_handle = Mock(return_value=foreground)
    editor.read = Mock(return_value=current)
    with pytest.raises(dialogs.DialogBlocked, match="foreground"):
        editor.acknowledge(known())
    window.set_focus.assert_called_once()
    window.descendants.assert_not_called()


def test_only_verified_foreground_modal_button_is_clicked():
    editor = object.__new__(dialogs.EditorDialogs)
    window, button = Mock(), Mock()
    window.descendants.return_value = [button]
    button.is_visible.return_value = True
    editor._windows = Mock(return_value=[window])
    editor._snapshot = Mock(return_value=known())
    editor._foreground_handle = Mock(return_value=123)
    editor.read = Mock(return_value=(known(),))
    editor.acknowledge(known())
    button.click_input.assert_called_once_with()
    button.invoke.assert_not_called()


def test_cli_dry_run_records_evidence_without_action(monkeypatch):
    editor = Mock()
    editor.read.return_value = [known()]
    editor.evidence.return_value = "private-status.json"
    monkeypatch.setattr(dialogs, "EditorDialogs", Mock(return_value=editor))
    assert dialogs.main(["--pid", "123"]) == 0
    editor.acknowledge.assert_not_called()
    assert editor.evidence.call_args.args[1]["status"] == "known-information"


def test_cli_unknown_dialog_returns_blocked_and_saves_evidence(monkeypatch):
    editor = Mock()
    editor.read.return_value = [replace(known(), title="Overwrite NAM")]
    editor.evidence.return_value = "private-status.json"
    monkeypatch.setattr(dialogs, "EditorDialogs", Mock(return_value=editor))
    assert dialogs.main(["--pid", "123", "--ack-known-information"]) == 2
    editor.acknowledge.assert_not_called()
    assert editor.evidence.call_args.args[1]["status"] == "blocked"


def test_wrong_executable_prevents_attachment(monkeypatch):
    editor = object.__new__(dialogs.EditorDialogs)
    editor.pid = 123
    monkeypatch.setattr(dialogs, "process_path", lambda _: dialogs.Path("other.exe"))
    with pytest.raises(dialogs.DialogBlocked, match="executable"):
        editor._identity()
