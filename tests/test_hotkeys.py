"""Global hotkey service tests."""

from __future__ import annotations

import sys

import pytest

from estudai.services.hotkeys import (
    DEFAULT_HOTKEY_BINDINGS,
    GlobalHotkeyService,
    HotkeyAction,
    HotkeyRegistrationError,
)


class _FakeHotkeyBackend:
    """Simple in-memory backend used to test service behavior."""

    def __init__(self) -> None:
        self.fail_bindings: set[str] = set()
        self.active_handles: dict[str, tuple[str, object]] = {}
        self.registered_bindings: list[str] = []
        self._next_handle = 0

    def register(self, binding: str, callback) -> object:
        if binding in self.fail_bindings:
            msg = f"Could not register '{binding}': already in use"
            raise HotkeyRegistrationError(msg)
        handle = f"handle-{self._next_handle}"
        self._next_handle += 1
        self.active_handles[handle] = (binding, callback)
        self.registered_bindings.append(binding)
        return handle

    def unregister(self, handle: object) -> None:
        self.active_handles.pop(str(handle), None)

    def trigger(self, binding: str) -> None:
        for registered_binding, callback in self.active_handles.values():
            if registered_binding == binding:
                callback()
                return
        msg = f"No binding registered for {binding}"
        raise AssertionError(msg)


def test_global_hotkey_service_applies_bindings_and_dispatches_callbacks() -> None:
    """Verify registration stores normalized bindings and fires mapped actions."""
    backend = _FakeHotkeyBackend()
    service = GlobalHotkeyService(backend=backend)
    triggered: list[HotkeyAction] = []

    service.apply_bindings(
        DEFAULT_HOTKEY_BINDINGS,
        {
            action: lambda action=action: triggered.append(action)
            for action in HotkeyAction
        },
    )

    assert service.active_bindings() == {
        HotkeyAction.PAUSE_RESUME: "ctrl+alt+space",
        HotkeyAction.START_STOP: "ctrl+alt+enter",
        HotkeyAction.MARK_CORRECT: "ctrl+alt+up",
        HotkeyAction.MARK_WRONG: "ctrl+alt+down",
    }

    backend.trigger("ctrl+alt+space")
    backend.trigger("ctrl+alt+down")

    assert triggered == [HotkeyAction.PAUSE_RESUME, HotkeyAction.MARK_WRONG]


def test_global_hotkey_service_rejects_duplicate_bindings_before_registration() -> None:
    """Verify duplicate action bindings fail before touching the backend."""
    backend = _FakeHotkeyBackend()
    service = GlobalHotkeyService(backend=backend)

    with pytest.raises(HotkeyRegistrationError, match="Hotkeys must be unique"):
        service.apply_bindings(
            {
                HotkeyAction.PAUSE_RESUME: "Ctrl+Alt+Space",
                HotkeyAction.START_STOP: "Ctrl+Alt+Space",
                HotkeyAction.MARK_CORRECT: "Ctrl+Alt+Up",
                HotkeyAction.MARK_WRONG: "Ctrl+Alt+Down",
            },
            {action: lambda: None for action in HotkeyAction},
        )

    assert backend.registered_bindings == []


def test_global_hotkey_service_restores_previous_bindings_after_failed_update() -> None:
    """Verify failed re-registration leaves the last valid hotkey set active."""
    backend = _FakeHotkeyBackend()
    service = GlobalHotkeyService(backend=backend)
    triggered: list[str] = []
    callbacks = {
        action: lambda action=action: triggered.append(action.value)
        for action in HotkeyAction
    }

    service.apply_bindings(DEFAULT_HOTKEY_BINDINGS, callbacks)
    backend.fail_bindings.add("ctrl+alt+f")

    with pytest.raises(HotkeyRegistrationError, match="ctrl\\+alt\\+f"):
        service.apply_bindings(
            {
                HotkeyAction.PAUSE_RESUME: "Ctrl+Alt+F",
                HotkeyAction.START_STOP: "Ctrl+Alt+Enter",
                HotkeyAction.MARK_CORRECT: "Ctrl+Alt+Up",
                HotkeyAction.MARK_WRONG: "Ctrl+Alt+Down",
            },
            callbacks,
        )

    assert service.active_bindings() == {
        HotkeyAction.PAUSE_RESUME: "ctrl+alt+space",
        HotkeyAction.START_STOP: "ctrl+alt+enter",
        HotkeyAction.MARK_CORRECT: "ctrl+alt+up",
        HotkeyAction.MARK_WRONG: "ctrl+alt+down",
    }

    backend.trigger("ctrl+alt+space")

    assert triggered == [HotkeyAction.PAUSE_RESUME.value]


def test_default_service_is_disabled_in_offscreen_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the runtime backend stays disabled for offscreen/CI sessions."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")

    service = GlobalHotkeyService()

    assert service.availability_error == (
        "Global hotkeys are unavailable while Qt runs in offscreen mode."
    )


def test_default_service_requires_x11_display_on_linux(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify Linux backend selection rejects sessions without an X11 display."""
    if not sys.platform.startswith("linux"):
        pytest.skip("Linux-only backend selection test.")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)

    service = GlobalHotkeyService()

    assert service.availability_error == (
        "Linux global hotkeys are supported only in X11 sessions with DISPLAY set."
    )
