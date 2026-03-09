"""Runtime-only study session state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from estudai.services.csv_flashcards import Flashcard
from estudai.services.settings import (
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
)

__all__ = [
    "SessionCardCounters",
    "SessionProgress",
    "StudyCardState",
    "StudySessionController",
]


class StudyCardState(StrEnum):
    """Explicit per-card study lifecycle for the active session."""

    PENDING = "pending"
    WRONG_PENDING = "wrong_pending"
    COMPLETED = "completed"


@dataclass
class SessionCardCounters:
    """Per-card scoring counters for the active session."""

    wrong_count: int = 0
    correct_count: int = 0


@dataclass(frozen=True)
class SessionProgress:
    """Snapshot of current study progress for UI rendering."""

    total_count: int
    completed_count: int
    remaining_count: int
    wrong_pending_count: int


class StudySessionController:
    """Manage the runtime state and retry queue for one scored study session."""

    def __init__(self) -> None:
        """Initialize an idle session controller."""
        self.flashcards: list[Flashcard] = []
        self.card_states: list[StudyCardState] = []
        self.card_counters: list[SessionCardCounters] = []
        self._upcoming_indexes: list[int] = []
        self.current_flashcard_index: int | None = None
        self.active = False
        self.wrong_answer_completion_mode = WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE
        self.wrong_answer_reinsertion_mode = WrongAnswerReinsertionMode.PUSH_TO_END
        self.wrong_answer_reinsert_after_count = 3

    def start(
        self,
        flashcards: list[Flashcard],
        *,
        wrong_answer_completion_mode: WrongAnswerCompletionMode,
        wrong_answer_reinsertion_mode: WrongAnswerReinsertionMode,
        wrong_answer_reinsert_after_count: int,
        random_order: bool,
        choice_func: Callable[[list[int]], int],
    ) -> bool:
        """Start a new session for the provided flashcard snapshot."""
        self.flashcards = list(flashcards)
        self.card_states = [StudyCardState.PENDING for _ in self.flashcards]
        self.card_counters = [SessionCardCounters() for _ in self.flashcards]
        self.current_flashcard_index = None
        self.wrong_answer_completion_mode = wrong_answer_completion_mode
        self.wrong_answer_reinsertion_mode = wrong_answer_reinsertion_mode
        self.wrong_answer_reinsert_after_count = max(
            0, int(wrong_answer_reinsert_after_count)
        )
        self._upcoming_indexes = list(range(len(self.flashcards)))
        if random_order:
            self._upcoming_indexes = self._randomized_indexes(choice_func)
        self.active = bool(self.flashcards)
        return self.active

    def reset(self) -> None:
        """Abort the current session and clear runtime-only state."""
        self.flashcards = []
        self.card_states = []
        self.card_counters = []
        self._upcoming_indexes = []
        self.current_flashcard_index = None
        self.active = False

    def next_flashcard(self) -> Flashcard | None:
        """Return and track the next flashcard queued for this session."""
        if not self._upcoming_indexes:
            self.current_flashcard_index = None
            return None
        flashcard_index = self._upcoming_indexes.pop(0)
        self.current_flashcard_index = flashcard_index
        return self.flashcards[flashcard_index]

    def queued_flashcard_indexes(self) -> list[int]:
        """Return a copy of the remaining queue order."""
        return list(self._upcoming_indexes)

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
        active_indexes = list(self._upcoming_indexes)
        if (
            self.current_flashcard_index is not None
            and self.card_states[self.current_flashcard_index]
            is not StudyCardState.COMPLETED
            and self.current_flashcard_index not in active_indexes
        ):
            active_indexes.insert(0, self.current_flashcard_index)
        return active_indexes

    def apply_current_score(self, score: str | None) -> bool:
        """Apply the finished answer state to the current card and queue."""
        if self.current_flashcard_index is None:
            return False

        flashcard_index = self.current_flashcard_index
        counters = self.card_counters[flashcard_index]

        if score == "wrong":
            counters.wrong_count += 1
            self.card_states[flashcard_index] = StudyCardState.WRONG_PENDING
            self._reinsert_flashcard(
                flashcard_index,
                use_wrong_answer_rule=True,
            )
        elif score == "correct":
            counters.correct_count += 1
            if self._is_completed(flashcard_index):
                self.card_states[flashcard_index] = StudyCardState.COMPLETED
            else:
                self.card_states[flashcard_index] = self._pending_state_for(
                    flashcard_index
                )
                self._reinsert_flashcard(
                    flashcard_index,
                    use_wrong_answer_rule=False,
                )
        else:
            self.card_states[flashcard_index] = self._pending_state_for(flashcard_index)
            self._reinsert_flashcard(
                flashcard_index,
                use_wrong_answer_rule=False,
            )

        self.current_flashcard_index = None
        return True

    def mark_current_correct(self) -> bool:
        """Mark the active flashcard according to the correct-answer rule."""
        return self.apply_current_score("correct")

    def mark_current_wrong(self) -> bool:
        """Mark the active flashcard according to the wrong-answer rule."""
        return self.apply_current_score("wrong")

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

    def _is_completed(self, flashcard_index: int) -> bool:
        """Return whether the card satisfies the configured completion rule."""
        counters = self.card_counters[flashcard_index]
        if (
            self.wrong_answer_completion_mode
            is WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
        ):
            return counters.correct_count > counters.wrong_count
        return counters.correct_count >= 1

    def _pending_state_for(self, flashcard_index: int) -> StudyCardState:
        """Return the pending state for an incomplete card."""
        counters = self.card_counters[flashcard_index]
        if counters.wrong_count > 0:
            return StudyCardState.WRONG_PENDING
        return StudyCardState.PENDING

    def _reinsert_flashcard(
        self,
        flashcard_index: int,
        *,
        use_wrong_answer_rule: bool,
    ) -> None:
        """Reinsert an incomplete flashcard back into the active queue."""
        if (
            use_wrong_answer_rule
            and self.wrong_answer_reinsertion_mode
            is WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS
        ):
            queue_index = min(
                self.wrong_answer_reinsert_after_count,
                len(self._upcoming_indexes),
            )
            self._upcoming_indexes.insert(queue_index, flashcard_index)
            return
        self._upcoming_indexes.append(flashcard_index)

    def _randomized_indexes(
        self,
        choice_func: Callable[[list[int]], int],
    ) -> list[int]:
        """Build a deterministic random order using the provided chooser."""
        randomized: list[int] = []
        remaining_indexes = list(range(len(self.flashcards)))
        while remaining_indexes:
            selected_index = choice_func(remaining_indexes)
            if selected_index not in remaining_indexes:
                selected_index = remaining_indexes[0]
            remaining_indexes.remove(selected_index)
            randomized.append(selected_index)
        return randomized
