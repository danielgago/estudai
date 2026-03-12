"""Study-session retry and queue behavior tests."""

from pathlib import Path

from estudai.services.csv_flashcards import Flashcard
from estudai.services.settings import (
    StudyOrderMode,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
)
from estudai.ui.study_session import StudyCardState, StudySessionController


def _flashcards(count: int) -> list[Flashcard]:
    """Build a small deterministic flashcard set for session tests."""
    return [
        Flashcard(
            question=f"Q{index}?",
            answer=f"A{index}.",
            source_file=Path("cards.csv"),
            source_line=index + 1,
        )
        for index in range(count)
    ]


def _start_session(
    flashcard_count: int,
    *,
    study_order_mode: StudyOrderMode = StudyOrderMode.QUEUE,
    queue_start_shuffled: bool = False,
    completion_mode: WrongAnswerCompletionMode = (
        WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE
    ),
    reinsertion_mode: WrongAnswerReinsertionMode = (
        WrongAnswerReinsertionMode.PUSH_TO_END
    ),
    reinsert_after_count: int = 3,
) -> StudySessionController:
    """Create and start a study session with configurable retry rules."""
    session = StudySessionController()
    started = session.start(
        _flashcards(flashcard_count),
        study_order_mode=study_order_mode,
        queue_start_shuffled=queue_start_shuffled,
        wrong_answer_completion_mode=completion_mode,
        wrong_answer_reinsertion_mode=reinsertion_mode,
        wrong_answer_reinsert_after_count=reinsert_after_count,
        choice_func=lambda indexes: indexes[-1],
    )

    assert started is True
    return session


def test_retry_mode_a_completes_after_one_correct_retry() -> None:
    """Verify Mode A completes a wrong card after the next correct answer."""
    session = _start_session(2)

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True
    assert session.card_states[0] is StudyCardState.WRONG_PENDING
    assert session.queued_flashcard_indexes() == [1, 0]

    assert session.next_flashcard().question == "Q1?"
    assert session.apply_current_score("correct") is True
    assert session.card_states[1] is StudyCardState.COMPLETED

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("correct") is True
    assert session.card_states[0] is StudyCardState.COMPLETED
    assert session.is_complete() is True


def test_retry_mode_b_requires_more_correct_than_wrong() -> None:
    """Verify Mode B keeps a card active until correct answers exceed wrong answers."""
    session = _start_session(
        1,
        completion_mode=WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG,
    )

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True
    assert session.card_counters[0].wrong_count == 1
    assert session.card_states[0] is StudyCardState.WRONG_PENDING
    assert session.queued_flashcard_indexes() == [0]

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("correct") is True
    assert session.card_counters[0].correct_count == 1
    assert session.card_states[0] is StudyCardState.WRONG_PENDING
    assert session.queued_flashcard_indexes() == [0]

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("correct") is True
    assert session.card_counters[0].correct_count == 2
    assert session.card_states[0] is StudyCardState.COMPLETED


def test_wrong_answer_reinsert_after_x_places_card_after_requested_gap() -> None:
    """Verify wrong cards are reinserted after X upcoming flashcards."""
    session = _start_session(
        4,
        reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        reinsert_after_count=1,
    )

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True

    assert session.queued_flashcard_indexes() == [1, 0, 2, 3]


def test_wrong_answer_reinsert_after_zero_shows_card_again_immediately() -> None:
    """Verify After-X zero reinserts the wrong card at the front of the queue."""
    session = _start_session(
        3,
        reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        reinsert_after_count=0,
    )

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True

    assert session.queued_flashcard_indexes() == [0, 1, 2]


def test_wrong_answer_reinsert_after_x_pushes_to_end_when_gap_is_too_large() -> None:
    """Verify large X values fall back to queue-end reinsertion."""
    session = _start_session(
        3,
        reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        reinsert_after_count=10,
    )

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True

    assert session.queued_flashcard_indexes() == [1, 2, 0]


def test_repeated_wrong_answers_keep_card_in_queue_without_dropping_it() -> None:
    """Verify repeated wrong answers preserve the card and accumulate counters."""
    session = _start_session(1)

    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True
    assert session.next_flashcard().question == "Q0?"
    assert session.apply_current_score("wrong") is True

    assert session.card_counters[0].wrong_count == 2
    assert session.card_states[0] is StudyCardState.WRONG_PENDING
    assert session.queued_flashcard_indexes() == [0]


def test_queue_shuffle_builds_predictable_initial_queue_and_keeps_wrong_card_active() -> (
    None
):
    """Verify queue shuffling preserves deterministic retry behavior."""
    session = _start_session(
        3,
        queue_start_shuffled=True,
        reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        reinsert_after_count=1,
    )

    assert session.queued_flashcard_indexes() == [2, 1, 0]
    assert session.next_flashcard().question == "Q2?"
    assert session.apply_current_score("wrong") is True

    assert session.queued_flashcard_indexes() == [1, 2, 0]
    assert session.next_flashcard().question == "Q1?"


def test_true_random_repeats_from_active_pool_without_queue_reinsertion() -> None:
    """Verify true-random mode draws from active cards instead of a managed queue."""
    session = _start_session(
        3,
        study_order_mode=StudyOrderMode.TRUE_RANDOM,
        reinsertion_mode=WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS,
        reinsert_after_count=1,
    )

    assert session.next_flashcard().question == "Q2?"
    assert session.apply_current_score("wrong") is True
    assert session.queued_flashcard_indexes() == [0, 1, 2]

    # The same wrong card can be picked again immediately because every draw
    # comes from the active pool rather than a reinserted queue position.
    assert session.next_flashcard().question == "Q2?"


def test_shuffle_remaining_queue_only_reorders_upcoming_queue() -> None:
    """Verify runtime queue shuffling leaves the active flashcard untouched."""
    session = _start_session(4)

    assert session.next_flashcard().question == "Q0?"
    assert session.shuffle_remaining_queue() is True
    assert session.current_flashcard_index == 0
    assert session.queued_flashcard_indexes() == [3, 2, 1]


def test_shuffle_remaining_queue_is_disabled_in_true_random_mode() -> None:
    """Verify queue shuffling is unavailable outside queue mode."""
    session = _start_session(
        3,
        study_order_mode=StudyOrderMode.TRUE_RANDOM,
    )

    assert session.shuffle_remaining_queue() is False


def test_replace_current_flashcard_updates_future_retries() -> None:
    """Verify editing the active flashcard updates the session payload in place."""
    session = _start_session(1)
    original = session.next_flashcard()
    assert original is not None

    updated = Flashcard(
        question="Updated question?",
        answer="Updated answer.",
        source_file=Path("_estudai_flashcards.csv"),
        source_line=1,
    )

    assert session.replace_current_flashcard(updated) is True
    assert session.current_flashcard() == updated

    assert session.apply_current_score("wrong") is True
    retried = session.next_flashcard()

    assert retried == updated


def test_remove_current_flashcard_reindexes_remaining_queue() -> None:
    """Verify deleting the active flashcard removes it without orphaning queue state."""
    session = _start_session(3)

    assert session.next_flashcard().question == "Q0?"
    assert session.remove_current_flashcard() is True
    assert session.current_flashcard() is None
    assert session.queued_flashcard_indexes() == [0, 1]

    next_flashcard = session.next_flashcard()
    assert next_flashcard is not None
    assert next_flashcard.question == "Q1?"


def test_replace_flashcards_updates_matching_session_cards() -> None:
    """Verify session metadata can be refreshed after one folder is persisted."""
    session = _start_session(3)

    replacements = {
        session.flashcards[1]: Flashcard(
            question="Q1?",
            answer="A1.",
            source_file=Path("_estudai_flashcards.csv"),
            source_line=1,
        ),
        session.flashcards[2]: Flashcard(
            question="Q2?",
            answer="A2.",
            source_file=Path("_estudai_flashcards.csv"),
            source_line=2,
        ),
    }

    session.replace_flashcards(replacements)

    assert session.flashcards[0].source_file == Path("cards.csv")
    assert session.flashcards[1].source_file == Path("_estudai_flashcards.csv")
    assert session.flashcards[1].source_line == 1
    assert session.flashcards[2].source_line == 2
