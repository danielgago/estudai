"""Flashcard mutation controller for active study sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6.QtWidgets import QDialog, QWidget

from estudai.services.csv_flashcards import (
    Flashcard,
    delete_flashcards_from_folder,
    update_flashcard_in_folder,
)
from estudai.ui.application_state import StudyApplicationState
from estudai.ui.pages import TimerPage
from estudai.ui.study_session import StudySessionController

CheckedFolderIdsGetter = Callable[[], set[str]]
HandleFolderDataChanged = Callable[[set[str] | None, str | None], None]
EditDialogFactory = Callable[[str, str, str | None, str | None, Path], object]
ShowWarningMessage = Callable[[str, str], None]
ConfirmAction = Callable[[str, str], bool]


@dataclass(frozen=True)
class CurrentFlashcardLocation:
    """Location metadata for the active flashcard across UI and storage."""

    session_flashcard_index: int
    folder_id: str
    folder_flashcard_index: int
    folder_path: Path
    flashcard: Flashcard


class _FlashcardSequenceState(Protocol):
    """Protocol for the flashcard sequence state used during mutation flows."""

    sequence_paused: bool


class SessionMutationRuntime(Protocol):
    """Protocol for timer runtime state mutated by edit/delete actions."""

    @property
    def study_session(self) -> StudySessionController:
        """Return the active study-session controller."""

    @property
    def active_study_session_keys(self) -> list[tuple[str, str]]:
        """Return folder/card keys for the active session order."""

    @active_study_session_keys.setter
    def active_study_session_keys(self, value: list[tuple[str, str]]) -> None:
        """Persist folder/card keys for the active session order."""

    @property
    def pending_flashcard_score(self) -> str | None:
        """Return the queued score for the active flashcard."""

    @pending_flashcard_score.setter
    def pending_flashcard_score(self, value: str | None) -> None:
        """Persist the queued score for the active flashcard."""

    @property
    def visible_flashcard(self) -> Flashcard | None:
        """Return the flashcard currently displayed on the timer page."""

    @visible_flashcard.setter
    def visible_flashcard(self, value: Flashcard | None) -> None:
        """Persist the flashcard currently displayed on the timer page."""

    @property
    def flashcard_sequence(self) -> _FlashcardSequenceState:
        """Return the flashcard sequence runtime state."""

    def cancel_flashcard_phase_timer(self) -> None:
        """Stop any active flashcard phase timer."""

    def update_study_session_progress(self) -> None:
        """Refresh visible study-session progress."""

    def complete_study_session(self) -> None:
        """Finish the active study session and reset timer UI state."""


class SessionMutationController:
    """Coordinate paused flashcard edit/delete workflows during study."""

    def __init__(
        self,
        *,
        parent: QWidget,
        timer_page: TimerPage,
        app_state: StudyApplicationState,
        runtime: SessionMutationRuntime,
        checked_folder_ids_getter: CheckedFolderIdsGetter,
        handle_folder_data_changed: HandleFolderDataChanged,
        edit_dialog_factory: EditDialogFactory,
        show_warning_message: ShowWarningMessage,
        confirm_action: ConfirmAction,
    ) -> None:
        """Initialize the controller.

        Args:
            parent: Parent widget used for modal dialogs.
            timer_page: Timer page that displays the active flashcard.
            app_state: Shared folder-backed application state.
            runtime: Timer runtime state mutated by edit/delete actions.
            checked_folder_ids_getter: Returns currently checked folder ids.
            handle_folder_data_changed: Reloads folder data while preserving
                checked and selected folder state.
            edit_dialog_factory: Creates the inline flashcard edit dialog.
            show_warning_message: Displays warning dialogs.
            confirm_action: Asks the user to confirm destructive actions.
        """
        self._parent = parent
        self._timer_page = timer_page
        self._app_state = app_state
        self._runtime = runtime
        self._checked_folder_ids_getter = checked_folder_ids_getter
        self._handle_folder_data_changed = handle_folder_data_changed
        self._edit_dialog_factory = edit_dialog_factory
        self._show_warning_message = show_warning_message
        self._confirm_action = confirm_action

    def handle_flashcard_edit_requested(self) -> None:
        """Edit the paused flashcard and update the active session immediately."""
        location = self._resolve_current_flashcard_location()
        if location is None:
            self._show_warning_message(
                "Edit flashcard",
                "The current flashcard is unavailable. Refresh and try again.",
            )
            return

        dialog = self._edit_dialog_factory(
            location.flashcard.question,
            location.flashcard.answer,
            location.flashcard.question_image_path,
            location.flashcard.answer_image_path,
            location.folder_path,
        )
        if dialog.exec() != QDialog.Accepted:
            return

        previous_folder_flashcards = list(
            self._app_state.flashcards_by_folder.get(location.folder_id, [])
        )
        try:
            updated_flashcards = update_flashcard_in_folder(
                location.folder_path,
                location.folder_flashcard_index,
                dialog.question_text(),
                dialog.answer_text(),
                question_image_path=dialog.question_image_path(),
                answer_image_path=dialog.answer_image_path(),
            )
        except (IndexError, ValueError) as error:
            self._show_warning_message("Edit flashcard", str(error))
            self._refresh_flashcard_data_after_mutation(location.folder_id)
            return

        updated_flashcard = updated_flashcards[location.folder_flashcard_index]
        if not self._runtime.study_session.replace_current_flashcard(updated_flashcard):
            self._show_warning_message(
                "Edit flashcard",
                "The current study session is no longer active.",
            )
            return
        self._sync_session_flashcards_for_folder(
            previous_folder_flashcards,
            updated_flashcards,
        )
        self._refresh_flashcard_data_after_mutation(location.folder_id)
        self._runtime.visible_flashcard = updated_flashcard
        self._timer_page.update_displayed_flashcard(
            updated_flashcard.question,
            updated_flashcard.answer,
            self._resolved_image_path(
                location.folder_path,
                updated_flashcard.question_image_path,
            ),
            self._resolved_image_path(
                location.folder_path,
                updated_flashcard.answer_image_path,
            ),
        )

    def handle_flashcard_delete_requested(self) -> None:
        """Delete the paused flashcard and remove it from the active session."""
        location = self._resolve_current_flashcard_location()
        if location is None:
            self._show_warning_message(
                "Delete flashcard",
                "The current flashcard is unavailable. Refresh and try again.",
            )
            return

        if not self._confirm_action(
            "Delete flashcard",
            "Delete the current flashcard?",
        ):
            return

        previous_folder_flashcards = list(
            self._app_state.flashcards_by_folder.get(location.folder_id, [])
        )
        try:
            updated_flashcards = delete_flashcards_from_folder(
                location.folder_path,
                [location.folder_flashcard_index],
            )
        except IndexError as error:
            self._show_warning_message("Delete flashcard", str(error))
            self._refresh_flashcard_data_after_mutation(location.folder_id)
            return

        selected_indexes = self._app_state.selected_indexes_after_deletion(
            location.folder_id,
            location.folder_flashcard_index,
        )
        self._runtime.cancel_flashcard_phase_timer()
        self._runtime.flashcard_sequence.sequence_paused = False
        self._runtime.pending_flashcard_score = None
        self._runtime.visible_flashcard = None
        if not self._runtime.study_session.remove_current_flashcard():
            self._show_warning_message(
                "Delete flashcard",
                "The current study session is no longer active.",
            )
            self._refresh_flashcard_data_after_mutation(
                location.folder_id,
                selected_indexes=selected_indexes,
            )
            return
        if (
            0
            <= location.session_flashcard_index
            < len(self._runtime.active_study_session_keys)
        ):
            updated_keys = list(self._runtime.active_study_session_keys)
            updated_keys.pop(location.session_flashcard_index)
            self._runtime.active_study_session_keys = updated_keys
        self._sync_session_flashcards_for_folder(
            previous_folder_flashcards,
            updated_flashcards,
            removed_flashcard_index=location.folder_flashcard_index,
        )
        self._refresh_flashcard_data_after_mutation(
            location.folder_id,
            selected_indexes=selected_indexes,
        )
        self._runtime.update_study_session_progress()
        if self._runtime.study_session.progress().remaining_count <= 0:
            self._runtime.complete_study_session()
            return
        self._timer_page.prepare_next_timer_cycle_paused()

    def _resolve_current_flashcard_location(self) -> CurrentFlashcardLocation | None:
        """Return folder/storage metadata for the flashcard active in the session."""
        current_flashcard = self._runtime.study_session.current_flashcard()
        session_flashcard_index = self._runtime.study_session.current_flashcard_index
        if current_flashcard is None or session_flashcard_index is None:
            return None

        for (
            folder_id,
            folder_flashcards,
        ) in self._app_state.flashcards_by_folder.items():
            try:
                folder_flashcard_index = folder_flashcards.index(current_flashcard)
            except ValueError:
                continue
            folder_path = self._app_state.persisted_folder_paths.get(folder_id)
            if folder_path is None:
                continue
            return CurrentFlashcardLocation(
                session_flashcard_index=session_flashcard_index,
                folder_id=folder_id,
                folder_flashcard_index=folder_flashcard_index,
                folder_path=folder_path,
                flashcard=current_flashcard,
            )
        return None

    def _refresh_flashcard_data_after_mutation(
        self,
        folder_id: str,
        *,
        selected_indexes: set[int] | None = None,
    ) -> None:
        """Reload persisted flashcard data after one folder mutation."""
        checked_ids = self._checked_folder_ids_getter()
        if selected_indexes is not None:
            self._app_state.update_selected_indexes(folder_id, selected_indexes)
            if selected_indexes:
                checked_ids.add(folder_id)
            else:
                checked_ids.discard(folder_id)
        self._handle_folder_data_changed(checked_ids, None)

    def _sync_session_flashcards_for_folder(
        self,
        previous_folder_flashcards: list[Flashcard],
        updated_folder_flashcards: list[Flashcard],
        *,
        removed_flashcard_index: int | None = None,
    ) -> None:
        """Refresh remaining in-session cards for one mutated folder."""
        replacements: dict[Flashcard, Flashcard] = {}
        for flashcard_index, previous_flashcard in enumerate(
            previous_folder_flashcards
        ):
            if (
                removed_flashcard_index is not None
                and flashcard_index == removed_flashcard_index
            ):
                continue
            updated_index = flashcard_index
            if (
                removed_flashcard_index is not None
                and flashcard_index > removed_flashcard_index
            ):
                updated_index -= 1
            if not (0 <= updated_index < len(updated_folder_flashcards)):
                continue
            replacements[previous_flashcard] = updated_folder_flashcards[updated_index]
        self._runtime.study_session.replace_flashcards(replacements)

    def _resolved_image_path(
        self,
        folder_path: Path,
        image_path: str | None,
    ) -> str | None:
        """Return one absolute image path for timer-page rendering."""
        if image_path is None:
            return None
        candidate_path = Path(image_path)
        if candidate_path.is_absolute():
            return str(candidate_path)
        return str(folder_path / candidate_path)
