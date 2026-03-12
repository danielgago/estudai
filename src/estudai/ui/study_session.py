"""Runtime-only study session state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from estudai.services.csv_flashcards import Flashcard
from estudai.services.settings import (
    StudyOrderMode,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
)
from estudai.services.study_progress import is_review_complete

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
        self._choice_func: Callable[[list[int]], int] | None = None
        self.current_flashcard_index: int | None = None
        self.active = False
        self.study_order_mode = StudyOrderMode.QUEUE
        self.wrong_answer_completion_mode = WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE
        self.wrong_answer_reinsertion_mode = WrongAnswerReinsertionMode.PUSH_TO_END
        self.wrong_answer_reinsert_after_count = 3

    def start(
        self,
        flashcards: list[Flashcard],
        *,
        initial_counters: list[SessionCardCounters] | None = None,
        study_order_mode: StudyOrderMode,
        queue_start_shuffled: bool,
        wrong_answer_completion_mode: WrongAnswerCompletionMode,
        wrong_answer_reinsertion_mode: WrongAnswerReinsertionMode,
        wrong_answer_reinsert_after_count: int,
        choice_func: Callable[[list[int]], int],
    ) -> bool:
        """Start a new session for the provided flashcard snapshot."""
        self.flashcards = list(flashcards)
        self.wrong_answer_completion_mode = wrong_answer_completion_mode
        self.wrong_answer_reinsertion_mode = wrong_answer_reinsertion_mode
        self.wrong_answer_reinsert_after_count = max(
            0, int(wrong_answer_reinsert_after_count)
        )
        self.card_counters = self._build_initial_counters(
            len(self.flashcards),
            initial_counters=initial_counters,
        )
        self.card_states = [
            self._initial_state_for(index) for index in range(len(self.flashcards))
        ]
        self._choice_func = choice_func
        self.current_flashcard_index = None
        self.study_order_mode = study_order_mode
        self._upcoming_indexes = (
            [
                index
                for index, state in enumerate(self.card_states)
                if state is not StudyCardState.COMPLETED
            ]
            if self.study_order_mode is StudyOrderMode.QUEUE
            else []
        )
        if queue_start_shuffled and self.study_order_mode is StudyOrderMode.QUEUE:
            self._upcoming_indexes = self._shuffled_indexes(self._upcoming_indexes)
        self.active = any(
            state is not StudyCardState.COMPLETED for state in self.card_states
        )
        return self.active

    def _build_initial_counters(
        self,
        flashcard_count: int,
        *,
        initial_counters: list[SessionCardCounters] | None,
    ) -> list[SessionCardCounters]:
        """Return normalized counters for the starting flashcard snapshot."""
        if initial_counters is None:
            return [SessionCardCounters() for _ in range(flashcard_count)]
        normalized_counters = [
            SessionCardCounters(
                wrong_count=max(0, counter.wrong_count),
                correct_count=max(0, counter.correct_count),
            )
            for counter in initial_counters[:flashcard_count]
        ]
        if len(normalized_counters) < flashcard_count:
            normalized_counters.extend(
                SessionCardCounters()
                for _ in range(flashcard_count - len(normalized_counters))
            )
        return normalized_counters

    def reset(self) -> None:
        """Abort the current session and clear runtime-only state."""
        self.flashcards = []
        self.card_states = []
        self.card_counters = []
        self._upcoming_indexes = []
        self._choice_func = None
        self.current_flashcard_index = None
        self.active = False
        self.study_order_mode = StudyOrderMode.QUEUE

    def next_flashcard(self) -> Flashcard | None:
        """Return and track the next flashcard queued for this session."""
        if self.study_order_mode is StudyOrderMode.TRUE_RANDOM:
            active_indexes = [
                index
                for index, state in enumerate(self.card_states)
                if state is not StudyCardState.COMPLETED
            ]
            if not active_indexes:
                self.current_flashcard_index = None
                return None
            flashcard_index = self._choose_index(active_indexes)
        else:
            if not self._upcoming_indexes:
                self.current_flashcard_index = None
                return None
            flashcard_index = self._upcoming_indexes.pop(0)
        self.current_flashcard_index = flashcard_index
        return self.flashcards[flashcard_index]

    def queued_flashcard_indexes(self) -> list[int]:
        """Return remaining upcoming indexes for the active study mode."""
        if self.study_order_mode is StudyOrderMode.TRUE_RANDOM:
            return [
                index
                for index, state in enumerate(self.card_states)
                if state is not StudyCardState.COMPLETED
                and index != self.current_flashcard_index
            ]
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

    def replace_current_flashcard(self, flashcard: Flashcard) -> bool:
        """Replace the active flashcard payload without changing queue state."""
        if self.current_flashcard_index is None:
            return False
        if not (0 <= self.current_flashcard_index < len(self.flashcards)):
            self.current_flashcard_index = None
            return False
        self.flashcards[self.current_flashcard_index] = flashcard
        return True

    def remove_current_flashcard(self) -> bool:
        """Remove the active flashcard and normalize all queued indexes."""
        if self.current_flashcard_index is None:
            return False

        flashcard_index = self.current_flashcard_index
        if not (0 <= flashcard_index < len(self.flashcards)):
            self.current_flashcard_index = None
            return False

        self.flashcards.pop(flashcard_index)
        self.card_states.pop(flashcard_index)
        self.card_counters.pop(flashcard_index)
        self._upcoming_indexes = [
            queued_index - 1 if queued_index > flashcard_index else queued_index
            for queued_index in self._upcoming_indexes
            if queued_index != flashcard_index
        ]
        self.current_flashcard_index = None
        self.active = bool(self.flashcards)
        return True

    def replace_flashcards(self, replacements: dict[Flashcard, Flashcard]) -> None:
        """Replace one or many session flashcards while preserving runtime state."""
        if not replacements:
            return
        self.flashcards = [
            replacements.get(flashcard, flashcard) for flashcard in self.flashcards
        ]

    def active_flashcard_indexes(self) -> list[int]:
        """Return indexes still in play for the current session."""
        if self.study_order_mode is StudyOrderMode.TRUE_RANDOM:
            return [
                index
                for index, state in enumerate(self.card_states)
                if state is not StudyCardState.COMPLETED
            ]
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
            if self.study_order_mode is StudyOrderMode.QUEUE:
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
                if self.study_order_mode is StudyOrderMode.QUEUE:
                    self._reinsert_flashcard(
                        flashcard_index,
                        use_wrong_answer_rule=False,
                    )
        else:
            self.card_states[flashcard_index] = self._pending_state_for(flashcard_index)
            if self.study_order_mode is StudyOrderMode.QUEUE:
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

    def shuffle_remaining_queue(self) -> bool:
        """Shuffle only the remaining queue for queue-based sessions.

        Returns:
            bool: True when the queue order changed.
        """
        if (
            self.study_order_mode is not StudyOrderMode.QUEUE
            or len(self._upcoming_indexes) < 2
            or self._choice_func is None
        ):
            return False
        self._upcoming_indexes = self._shuffled_indexes(self._upcoming_indexes)
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

    def _is_completed(self, flashcard_index: int) -> bool:
        """Return whether the card satisfies the configured completion rule."""
        counters = self.card_counters[flashcard_index]
        return self._is_completed_from_counters(counters)

    def _is_completed_from_counters(self, counters: SessionCardCounters) -> bool:
        """Return whether counters satisfy the configured completion rule."""
        return is_review_complete(
            counters.correct_count,
            counters.wrong_count,
            self.wrong_answer_completion_mode,
        )

    def _initial_state_for(self, flashcard_index: int) -> StudyCardState:
        """Return the correct opening state for one flashcard."""
        counters = self.card_counters[flashcard_index]
        if self._is_completed_from_counters(counters):
            return StudyCardState.COMPLETED
        return self._pending_state_for(flashcard_index)

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

    def _choose_index(self, candidate_indexes: list[int]) -> int:
        """Choose one index using the configured picker with safe fallback."""
        if not candidate_indexes:
            msg = "candidate_indexes must not be empty"
            raise ValueError(msg)
        if self._choice_func is None:
            return candidate_indexes[0]
        selected_index = self._choice_func(candidate_indexes)
        if selected_index not in candidate_indexes:
            return candidate_indexes[0]
        return selected_index

    def _shuffled_indexes(self, indexes: list[int]) -> list[int]:
        """Build a deterministic shuffled copy using the configured chooser."""
        randomized: list[int] = []
        remaining_indexes = list(indexes)
        while remaining_indexes:
            selected_index = self._choose_index(remaining_indexes)
            remaining_indexes.remove(selected_index)
            randomized.append(selected_index)
        return randomized
