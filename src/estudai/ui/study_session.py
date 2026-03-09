"""Runtime-only study session state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from estudai.services.csv_flashcards import Flashcard

__all__ = [
    "SessionProgress",
    "StudyCardState",
    "StudySessionController",
]


class StudyCardState(StrEnum):
    """Explicit per-card study lifecycle for the active session."""

    PENDING = "pending"
    WRONG_PENDING = "wrong_pending"
    COMPLETED = "completed"


@dataclass(frozen=True)
class SessionProgress:
    """Snapshot of current study progress for UI rendering."""

    total_count: int
    completed_count: int
    remaining_count: int
    wrong_pending_count: int


class StudySessionController:
    """Manage the runtime state of one scored study session."""

    def __init__(self) -> None:
        """Initialize an idle session controller."""
        self.flashcards: list[Flashcard] = []
        self.card_states: list[StudyCardState] = []
        self.current_flashcard_index: int | None = None
        self.active = False

    def start(self, flashcards: list[Flashcard]) -> bool:
        """Start a new session for the provided flashcard snapshot."""
        self.flashcards = list(flashcards)
        self.card_states = [StudyCardState.PENDING for _ in self.flashcards]
        self.current_flashcard_index = None
        self.active = bool(self.flashcards)
        return self.active

    def reset(self) -> None:
        """Abort the current session and clear runtime-only state."""
        self.flashcards = []
        self.card_states = []
        self.current_flashcard_index = None
        self.active = False

    def set_current_flashcard(self, flashcard_index: int | None) -> Flashcard | None:
        """Track the flashcard currently being shown to the user."""
        if flashcard_index is None or not (0 <= flashcard_index < len(self.flashcards)):
            self.current_flashcard_index = None
            return None
        self.current_flashcard_index = flashcard_index
        return self.flashcards[flashcard_index]

    def current_flashcard(self) -> Flashcard | None:
        """Return the flashcard currently active in the session."""
        if self.current_flashcard_index is None:
            return None
        return self.flashcards[self.current_flashcard_index]

    def active_flashcard_indexes(self) -> list[int]:
        """Return indexes still in play for the current session."""
        return [
            flashcard_index
            for flashcard_index, state in enumerate(self.card_states)
            if state is not StudyCardState.COMPLETED
        ]

    def mark_current_correct(self) -> bool:
        """Mark the active flashcard as completed for this session."""
        if self.current_flashcard_index is None:
            return False
        self.card_states[self.current_flashcard_index] = StudyCardState.COMPLETED
        return True

    def mark_current_wrong(self) -> bool:
        """Mark the active flashcard for review later in this session."""
        if self.current_flashcard_index is None:
            return False
        self.card_states[self.current_flashcard_index] = StudyCardState.WRONG_PENDING
        return True

    def is_complete(self) -> bool:
        """Return whether every flashcard has been completed."""
        return self.active and all(
            state is StudyCardState.COMPLETED for state in self.card_states
        )

    def progress(self) -> SessionProgress:
        """Return a progress summary for the timer page."""
        total_count = len(self.card_states)
        completed_count = sum(
            state is StudyCardState.COMPLETED for state in self.card_states
        )
        wrong_pending_count = sum(
            state is StudyCardState.WRONG_PENDING for state in self.card_states
        )
        return SessionProgress(
            total_count=total_count,
            completed_count=completed_count,
            remaining_count=total_count - completed_count,
            wrong_pending_count=wrong_pending_count,
        )
