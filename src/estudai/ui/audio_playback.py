"""Shared helpers for timed audio playback."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal

try:
    from PySide6.QtMultimedia import QMediaPlayer
except ImportError:  # pragma: no cover - depends on system multimedia libraries.
    QMediaPlayer = None  # type: ignore[assignment]

__all__ = ["TimedAudioPlaybackController"]


class TimedAudioPlaybackController(QObject):
    """Wrap one media player with explicit stop and optional cutoff timing."""

    playback_started = Signal(object)
    playback_stopped = Signal(object)

    def __init__(self, parent: QObject | None = None, *, player: object | None = None):
        """Initialize the playback controller."""
        super().__init__(parent)
        self._player: object | None = None
        self._active_context: object | None = None
        self._stop_timer = QTimer(self)
        self._stop_timer.setSingleShot(True)
        self._stop_timer.timeout.connect(self.stop)
        self.set_player(player)

    @property
    def is_available(self) -> bool:
        """Return whether a concrete media player is available."""
        return self._player is not None

    @property
    def active_context(self) -> object | None:
        """Return the current playback context, if any."""
        return self._active_context

    def set_player(self, player: object | None) -> None:
        """Swap the underlying media player and reconnect state tracking."""
        if player is self._player:
            return
        self.stop()
        self._disconnect_state_signal(self._player)
        self._player = player
        self._connect_state_signal(self._player)

    def play(
        self,
        sound_path: Path,
        *,
        max_duration_ms: int | None = None,
        context: object | None = None,
    ) -> bool:
        """Start playback for one local file and trim it when requested."""
        if self._player is None:
            return False
        self.stop()
        self._active_context = context
        self._player.setSource(QUrl.fromLocalFile(str(sound_path)))
        self._player.play()
        if max_duration_ms is not None:
            clamped_duration_ms = max(0, int(max_duration_ms))
            if clamped_duration_ms <= 0:
                self.stop()
                return True
            self._stop_timer.start(clamped_duration_ms)
        self.playback_started.emit(context)
        return True

    def stop(self) -> bool:
        """Stop current playback and clear any active cutoff timer."""
        had_active_timer = self._stop_timer.isActive()
        if had_active_timer:
            self._stop_timer.stop()
        active_context = self._active_context
        self._active_context = None
        if self._player is not None and (
            active_context is not None or had_active_timer
        ):
            stop_method = getattr(self._player, "stop", None)
            if callable(stop_method):
                stop_method()
        if active_context is None:
            return False
        self.playback_stopped.emit(active_context)
        return True

    def _connect_state_signal(self, player: object | None) -> None:
        """Listen for player-driven stops when the backend exposes that signal."""
        playback_state_changed = getattr(player, "playbackStateChanged", None)
        connect = getattr(playback_state_changed, "connect", None)
        if callable(connect):
            connect(self._handle_playback_state_changed)

    def _disconnect_state_signal(self, player: object | None) -> None:
        """Detach from the old player signal when one was connected."""
        playback_state_changed = getattr(player, "playbackStateChanged", None)
        disconnect = getattr(playback_state_changed, "disconnect", None)
        if callable(disconnect):
            try:
                disconnect(self._handle_playback_state_changed)
            except (RuntimeError, TypeError):
                return

    def _handle_playback_state_changed(self, state: object) -> None:
        """Clear controller state when the media backend stops by itself."""
        if self._active_context is None:
            return
        if not self._is_stopped_state(state):
            return
        if self._stop_timer.isActive():
            self._stop_timer.stop()
        active_context = self._active_context
        self._active_context = None
        self.playback_stopped.emit(active_context)

    def _is_stopped_state(self, state: object) -> bool:
        """Return whether one playback-state value represents a stopped player."""
        if QMediaPlayer is not None:
            playback_state = getattr(QMediaPlayer, "PlaybackState", None)
            if playback_state is not None:
                return state == playback_state.StoppedState
            stopped_state = getattr(QMediaPlayer, "StoppedState", None)
            if stopped_state is not None:
                return state == stopped_state
        return getattr(state, "name", "") == "StoppedState" or state == 0
