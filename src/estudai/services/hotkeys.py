"""Platform-aware global hotkey registration helpers."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

__all__ = [
    "DEFAULT_HOTKEY_BINDINGS",
    "DisabledHotkeyBackend",
    "GlobalHotkeyService",
    "HotkeyAction",
    "HotkeyRegistrationError",
    "KeyboardHotkeyBackend",
    "X11HotkeyBackend",
    "normalize_hotkey_bindings",
]


class HotkeyAction(StrEnum):
    """Supported app actions that can be triggered by a global hotkey."""

    PAUSE_RESUME = "pause_resume"
    START_STOP = "start_stop"
    MARK_CORRECT = "mark_correct"
    MARK_WRONG = "mark_wrong"
    COPY_QUESTION = "copy_question"


DEFAULT_HOTKEY_BINDINGS: dict[HotkeyAction, str] = {
    HotkeyAction.PAUSE_RESUME: "Ctrl+Alt+Space",
    HotkeyAction.START_STOP: "Ctrl+Alt+Enter",
    HotkeyAction.MARK_CORRECT: "Ctrl+Alt+Up",
    HotkeyAction.MARK_WRONG: "Ctrl+Alt+Down",
    HotkeyAction.COPY_QUESTION: "Ctrl+Alt+C",
}

_MODIFIER_TOKENS = {"alt", "ctrl", "shift", "windows", "cmd", "command"}
_TOKEN_ALIASES = {
    "backtab": "tab",
    "command": "cmd",
    "control": "ctrl",
    "ctrl": "ctrl",
    "del": "delete",
    "delete": "delete",
    "down": "down",
    "enter": "enter",
    "esc": "esc",
    "escape": "esc",
    "ins": "insert",
    "left": "left",
    "meta": "windows",
    "option": "alt",
    "pgdown": "page_down",
    "pgup": "page_up",
    "return": "enter",
    "right": "right",
    "space": "space",
    "super": "windows",
    "tab": "tab",
    "up": "up",
    "win": "windows",
}
_X11_KEYSYM_ALIASES = {
    "cmd": "Super_L",
    "delete": "Delete",
    "down": "Down",
    "enter": "Return",
    "esc": "Escape",
    "insert": "Insert",
    "left": "Left",
    "page_down": "Next",
    "page_up": "Prior",
    "right": "Right",
    "space": "space",
    "tab": "Tab",
    "up": "Up",
    "windows": "Super_L",
}


class HotkeyRegistrationError(ValueError):
    """Raised when a hotkey binding cannot be validated or registered."""


class HotkeyBackend(Protocol):
    """Backend interface for registering system-wide hotkeys."""

    def register(self, binding: str, callback: Callable[[], None]) -> object:
        """Register a global hotkey and return an opaque handle."""

    def unregister(self, handle: object) -> None:
        """Unregister one previously registered global hotkey."""


@dataclass(frozen=True)
class _RegisteredHotkey:
    """One active hotkey registration tracked by the service."""

    binding: str
    callback: Callable[[], None]
    handle: object


@dataclass(frozen=True)
class X11KeyCombination:
    """One parsed X11 key combination."""

    keycode: int
    modifiers: int


@dataclass(frozen=True)
class X11RegistrationHandle:
    """Opaque X11 handle tracked by the service."""

    keycode: int
    grabbed_modifiers: tuple[int, ...]


def _normalize_hotkey_token(token: str) -> str:
    """Normalize one hotkey token into the backend-friendly form."""
    normalized = token.strip().lower()
    if not normalized:
        msg = "Hotkeys cannot contain empty key parts."
        raise HotkeyRegistrationError(msg)
    normalized = normalized.replace(" ", "_")
    normalized = _TOKEN_ALIASES.get(normalized, normalized)
    if len(normalized) == 1 and normalized.isalpha():
        return normalized
    if normalized.isdigit():
        return normalized
    return normalized


def normalize_hotkey_binding(binding: str, *, allow_empty: bool = False) -> str:
    """Normalize one user-provided hotkey binding string."""
    normalized_binding = binding.strip()
    if not normalized_binding:
        if allow_empty:
            return ""
        msg = "Hotkeys cannot be empty."
        raise HotkeyRegistrationError(msg)
    if "," in normalized_binding:
        msg = "Hotkeys must be a single key combination, not a sequence."
        raise HotkeyRegistrationError(msg)

    parts = [_normalize_hotkey_token(part) for part in normalized_binding.split("+")]
    if len(set(parts)) != len(parts):
        msg = f"Hotkey '{binding}' repeats the same key more than once."
        raise HotkeyRegistrationError(msg)
    if all(part in _MODIFIER_TOKENS for part in parts):
        msg = f"Hotkey '{binding}' must include a non-modifier key."
        raise HotkeyRegistrationError(msg)

    return "+".join(parts)


def normalize_hotkey_bindings(
    bindings: Mapping[HotkeyAction, str],
    *,
    allow_empty: bool = False,
) -> dict[HotkeyAction, str]:
    """Normalize all required app hotkey bindings and reject duplicates."""
    normalized_bindings: dict[HotkeyAction, str] = {}
    owners_by_binding: dict[str, HotkeyAction] = {}
    for action in HotkeyAction:
        binding = normalize_hotkey_binding(bindings[action], allow_empty=allow_empty)
        normalized_bindings[action] = binding
        if not binding:
            continue
        owner = owners_by_binding.get(binding)
        if owner is not None:
            msg = (
                "Hotkeys must be unique. "
                f"'{bindings[action]}' is assigned to both '{owner.value}' and "
                f"'{action.value}'."
            )
            raise HotkeyRegistrationError(msg)
        owners_by_binding[binding] = action
    return normalized_bindings


class DisabledHotkeyBackend:
    """Placeholder backend used when global hotkeys are unavailable."""

    def __init__(self, reason: str) -> None:
        """Store the availability reason."""
        self.reason = reason

    def register(self, binding: str, callback: Callable[[], None]) -> object:
        """Reject registration attempts with a clear message."""
        raise HotkeyRegistrationError(self.reason)

    def unregister(self, handle: object) -> None:
        """Ignore unregister calls for the disabled backend."""


class KeyboardHotkeyBackend:
    """`keyboard`-based backend used on Windows."""

    def __init__(self, keyboard_module: Any) -> None:
        """Store the imported module dependency."""
        self._keyboard = keyboard_module

    def register(self, binding: str, callback: Callable[[], None]) -> object:
        """Register one hotkey through `keyboard.add_hotkey`."""
        try:
            return self._keyboard.add_hotkey(binding, callback, suppress=False)
        except Exception as error:  # pragma: no cover - depends on host OS/hardware.
            msg = f"Could not register '{binding}': {error}"
            raise HotkeyRegistrationError(msg) from error

    def unregister(self, handle: object) -> None:
        """Unregister one `keyboard` hotkey handle."""
        try:
            self._keyboard.remove_hotkey(handle)
        except Exception:  # pragma: no cover - best-effort cleanup.
            return


class X11HotkeyBackend:
    """X11 key-grab backend for Linux sessions running under Xorg/Xwayland."""

    def __init__(
        self,
        *,
        display_module: Any,
        x_module: Any,
        xk_module: Any,
        error_module: Any,
    ) -> None:
        """Initialize the X11 display connection and event loop state."""
        try:
            self._display = display_module.Display()
        except Exception as error:  # pragma: no cover - depends on host display.
            msg = f"Could not connect to the X11 display: {error}"
            raise HotkeyRegistrationError(msg) from error

        self._X = x_module
        self._XK = xk_module
        self._error = error_module
        self._root = self._display.screen().root
        self._callbacks: dict[tuple[int, int], Callable[[], None]] = {}
        self._lock = threading.RLock()
        self._event_thread: threading.Thread | None = None
        self._modifier_mask = (
            self._X.ControlMask
            | self._X.ShiftMask
            | self._X.Mod1Mask
            | self._X.Mod4Mask
            | self._X.LockMask
            | self._detect_num_lock_mask()
        )

    def register(self, binding: str, callback: Callable[[], None]) -> object:
        """Grab one key combination on the X11 root window."""
        key_combination = self._parse_binding(binding)
        grabbed_modifiers = self._grabbed_modifier_variants(key_combination.modifiers)

        with self._lock:
            for modifiers in grabbed_modifiers:
                catcher = self._error.CatchError(self._error.BadAccess)
                self._root.grab_key(
                    key_combination.keycode,
                    modifiers,
                    True,
                    self._X.GrabModeAsync,
                    self._X.GrabModeAsync,
                    onerror=catcher,
                )
                self._display.sync()
                if catcher.get_error() is not None:
                    self._release_grabbed_variants(
                        key_combination.keycode,
                        grabbed_modifiers,
                    )
                    msg = (
                        f"Could not register '{binding}': "
                        "the binding is already in use on this X11 session."
                    )
                    raise HotkeyRegistrationError(msg)
                self._callbacks[(key_combination.keycode, modifiers)] = callback

            self._ensure_event_thread()
            self._display.flush()

        return X11RegistrationHandle(
            keycode=key_combination.keycode,
            grabbed_modifiers=grabbed_modifiers,
        )

    def unregister(self, handle: object) -> None:
        """Release one X11 key grab and remove its callbacks."""
        if not isinstance(handle, X11RegistrationHandle):
            return
        with self._lock:
            self._release_grabbed_variants(handle.keycode, handle.grabbed_modifiers)
            self._display.flush()

    def _release_grabbed_variants(
        self,
        keycode: int,
        grabbed_modifiers: tuple[int, ...],
    ) -> None:
        """Release a set of grabbed modifier variants."""
        for modifiers in grabbed_modifiers:
            self._callbacks.pop((keycode, modifiers), None)
            self._root.ungrab_key(keycode, modifiers)

    def _parse_binding(self, binding: str) -> X11KeyCombination:
        """Translate one normalized binding into X11 keycode and modifiers."""
        modifiers = 0
        non_modifier_tokens: list[str] = []
        for token in binding.split("+"):
            if token == "ctrl":
                modifiers |= self._X.ControlMask
                continue
            if token == "alt":
                modifiers |= self._X.Mod1Mask
                continue
            if token == "shift":
                modifiers |= self._X.ShiftMask
                continue
            if token in {"cmd", "windows"}:
                modifiers |= self._X.Mod4Mask
                continue
            non_modifier_tokens.append(token)

        if len(non_modifier_tokens) != 1:
            msg = f"Hotkey '{binding}' must contain exactly one non-modifier key."
            raise HotkeyRegistrationError(msg)

        token = non_modifier_tokens[0]
        keysym_name = _X11_KEYSYM_ALIASES.get(token, token)
        keysym = self._XK.string_to_keysym(keysym_name)
        if keysym == 0:
            msg = f"Hotkey '{binding}' uses an unsupported key."
            raise HotkeyRegistrationError(msg)
        keycode = self._display.keysym_to_keycode(keysym)
        if keycode == 0:
            msg = f"Hotkey '{binding}' could not be mapped on this keyboard layout."
            raise HotkeyRegistrationError(msg)
        return X11KeyCombination(keycode=keycode, modifiers=modifiers)

    def _detect_num_lock_mask(self) -> int:
        """Resolve the modifier mask used by Num Lock when available."""
        keysym = self._XK.string_to_keysym("Num_Lock")
        if keysym == 0:
            return 0
        keycode = self._display.keysym_to_keycode(keysym)
        if keycode == 0:
            return 0

        modifier_mapping = self._display.get_modifier_mapping()
        for modifier_index, keycodes in enumerate(modifier_mapping):
            if keycode in keycodes:
                return 1 << modifier_index
        return 0

    def _grabbed_modifier_variants(self, modifiers: int) -> tuple[int, ...]:
        """Build the exact modifier states to grab for one logical shortcut."""
        variants = {
            modifiers,
            modifiers | self._X.LockMask,
        }
        num_lock_mask = self._modifier_mask & ~(
            self._X.ControlMask
            | self._X.ShiftMask
            | self._X.Mod1Mask
            | self._X.Mod4Mask
            | self._X.LockMask
        )
        if num_lock_mask:
            variants.add(modifiers | num_lock_mask)
            variants.add(modifiers | self._X.LockMask | num_lock_mask)
        return tuple(sorted(variants))

    def _ensure_event_thread(self) -> None:
        """Start the X11 event loop once the first binding is active."""
        if self._event_thread is not None:
            return
        self._event_thread = threading.Thread(
            target=self._event_loop,
            name="estudai-x11-hotkeys",
            daemon=True,
        )
        self._event_thread.start()

    def _event_loop(self) -> None:
        """Block on X11 events and dispatch registered callbacks."""
        while True:
            try:
                event = self._display.next_event()
            except Exception:  # pragma: no cover - depends on host X11 lifecycle.
                return
            if event.type != self._X.KeyPress:
                continue
            state = event.state & self._modifier_mask
            with self._lock:
                callback = self._callbacks.get((event.detail, state))
            if callback is not None:
                callback()


def _build_windows_backend() -> HotkeyBackend:
    """Create the runtime backend for Windows."""
    try:
        import keyboard
    except ImportError:
        return DisabledHotkeyBackend(
            "Windows global hotkeys require the optional 'keyboard' package."
        )
    return KeyboardHotkeyBackend(keyboard)


def _build_linux_backend() -> HotkeyBackend:
    """Create the runtime backend for Linux/X11."""
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen":
        return DisabledHotkeyBackend(
            "Global hotkeys are unavailable while Qt runs in offscreen mode."
        )
    if not os.environ.get("DISPLAY"):
        return DisabledHotkeyBackend(
            "Linux global hotkeys are supported only in X11 sessions with DISPLAY set."
        )
    try:
        from Xlib import X, XK, display, error
    except ImportError:
        return DisabledHotkeyBackend(
            "Linux X11 global hotkeys require the optional 'python-xlib' package."
        )
    try:
        return X11HotkeyBackend(
            display_module=display,
            x_module=X,
            xk_module=XK,
            error_module=error,
        )
    except HotkeyRegistrationError as error:
        return DisabledHotkeyBackend(str(error))


def _build_default_backend() -> HotkeyBackend:
    """Create the runtime backend for the current platform."""
    if sys.platform.startswith("win"):
        return _build_windows_backend()
    if sys.platform.startswith("linux"):
        return _build_linux_backend()
    return DisabledHotkeyBackend(
        "Global hotkeys are only supported on Windows and Linux."
    )


class GlobalHotkeyService:
    """Manage the active set of registered global hotkeys."""

    def __init__(self, backend: HotkeyBackend | None = None) -> None:
        """Initialize the service with the selected backend."""
        self._backend = backend or _build_default_backend()
        self._registrations: dict[HotkeyAction, _RegisteredHotkey] = {}

    @property
    def availability_error(self) -> str | None:
        """Return the current backend availability message when disabled."""
        if isinstance(self._backend, DisabledHotkeyBackend):
            return self._backend.reason
        return None

    def active_bindings(self) -> dict[HotkeyAction, str]:
        """Return the current active binding for each registered action."""
        return {
            action: registration.binding
            for action, registration in self._registrations.items()
        }

    def clear(self) -> None:
        """Unregister every currently active hotkey."""
        for registration in self._registrations.values():
            self._backend.unregister(registration.handle)
        self._registrations.clear()

    def apply_bindings(
        self,
        bindings: Mapping[HotkeyAction, str],
        callbacks: Mapping[HotkeyAction, Callable[[], None]],
    ) -> dict[HotkeyAction, str]:
        """Replace the active hotkey set and roll back on failure."""
        normalized_bindings = normalize_hotkey_bindings(bindings, allow_empty=True)
        previous_registrations = dict(self._registrations)

        self.clear()
        try:
            for action in HotkeyAction:
                binding = normalized_bindings[action]
                if not binding:
                    continue
                handle = self._backend.register(
                    binding,
                    callbacks[action],
                )
                self._registrations[action] = _RegisteredHotkey(
                    binding=binding,
                    callback=callbacks[action],
                    handle=handle,
                )
        except HotkeyRegistrationError:
            self.clear()
            self._restore(previous_registrations)
            raise

        return self.active_bindings()

    def _restore(
        self,
        registrations: Mapping[HotkeyAction, _RegisteredHotkey],
    ) -> None:
        """Best-effort restoration of the previous valid registration set."""
        restored: dict[HotkeyAction, _RegisteredHotkey] = {}
        for action, registration in registrations.items():
            try:
                handle = self._backend.register(
                    registration.binding,
                    registration.callback,
                )
            except HotkeyRegistrationError:
                for restored_registration in restored.values():
                    self._backend.unregister(restored_registration.handle)
                self._registrations.clear()
                return
            restored[action] = _RegisteredHotkey(
                binding=registration.binding,
                callback=registration.callback,
                handle=handle,
            )
        self._registrations = restored
