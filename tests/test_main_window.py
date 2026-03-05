"""Main window tests."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton

from estudai.services.csv_flashcards import Flashcard
from estudai.services.folder_storage import list_persisted_folders
from estudai.services.settings import AppSettings
from estudai.ui.main_window import MainWindow


@pytest.fixture(scope="session")
def app() -> QApplication:
    """Return a QApplication instance for UI tests."""
    existing_app = QApplication.instance()
    if existing_app is not None:
        return existing_app
    return QApplication([])


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def test_main_window_registers_all_pages(app: QApplication) -> None:
    """Verify that all expected pages are present in the stack."""
    window = MainWindow()

    assert window.stacked_widget.count() == 3
    assert window.stacked_widget.currentWidget() is window.timer_page
    assert window.current_folder_name == "No folders selected"


def test_sidebar_toggle_changes_visibility(app: QApplication) -> None:
    """Verify that the sidebar toggle button opens and closes the sidebar."""
    window = MainWindow()

    assert window.sidebar.isHidden()
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()
    window.toggle_sidebar()
    assert window.sidebar.isHidden()


def test_sidebar_clicking_outside_closes_when_open(app: QApplication) -> None:
    """Verify clicks outside the sidebar close it."""
    window = MainWindow()
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()

    click_position = window.stacked_widget.mapToGlobal(
        window.stacked_widget.rect().center()
    )
    window._handle_global_click(click_position)

    assert window.sidebar.isHidden()


def test_sidebar_button_order_is_welcoming(app: QApplication) -> None:
    """Verify sidebar action order follows create -> NotebookLM -> import folder."""
    window = MainWindow()
    sidebar_layout = window.sidebar.layout()
    button_texts = [
        sidebar_layout.itemAt(index).widget().text()
        for index in range(sidebar_layout.count())
        if isinstance(sidebar_layout.itemAt(index).widget(), QPushButton)
    ]

    assert button_texts == [
        "Create Folder",
        "Import NotebookLM CSV",
        "Import Existing Folder",
    ]


def test_page_switching_methods_navigate_correctly(app: QApplication) -> None:
    """Verify that navigation methods point to the right page widgets."""
    window = MainWindow()

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.settings_page

    window.switch_to_settings()
    assert window.stacked_widget.currentWidget() is window.timer_page

    window.switch_to_timer()
    assert window.stacked_widget.currentWidget() is window.timer_page


def test_sidebar_folder_selection_updates_current_folder(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify folder checkbox updates selected flashcard scope."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\n",
        encoding="utf-8",
    )
    window.add_folder(biology_folder)
    folder_item = window.sidebar_folder_list.item(0)

    folder_item.setCheckState(Qt.Unchecked)
    assert window.current_folder_name == "No folders selected"
    assert len(window.loaded_flashcards) == 0

    folder_item.setCheckState(Qt.Checked)
    assert window.current_folder_name == "biology"
    assert len(window.loaded_flashcards) == 1


def test_add_folder_loads_csv_flashcards(app: QApplication, tmp_path: Path) -> None:
    """Verify adding a folder loads CSV flashcards and updates selection context."""
    window = MainWindow()
    flashcards_folder = tmp_path / "biology"
    flashcards_folder.mkdir()
    (flashcards_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\nWhat is RNA?,Messenger molecule.\n",
        encoding="utf-8",
    )

    added = window.add_folder(flashcards_folder)
    folder_item = window.sidebar_folder_list.item(0)
    window.handle_sidebar_folder_click(folder_item)
    persisted = list_persisted_folders()

    assert added is True
    assert window.sidebar_folder_list.count() == 1
    assert window.current_folder_name == "biology"
    assert len(window.loaded_flashcards) == 2
    assert len(persisted) == 1
    assert (Path(persisted[0].stored_path) / "cards.csv").exists()
    assert window.stacked_widget.currentWidget() is window.timer_page
    assert window.timer_page.folder_context_label.text() == "Folder: biology (2 cards)"


def test_folder_copy_persists_after_source_deletion(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify copied folder data is still available after source deletion."""
    source_folder = tmp_path / "Desktop" / "chemistry"
    source_folder.mkdir(parents=True)
    (source_folder / "cards.csv").write_text(
        "What is NaCl?,Salt.\n",
        encoding="utf-8",
    )

    first_window = MainWindow()
    assert first_window.add_folder(source_folder) is True
    shutil.rmtree(source_folder)

    second_window = MainWindow()
    assert second_window.sidebar_folder_list.count() == 1

    second_window.handle_sidebar_folder_click(second_window.sidebar_folder_list.item(0))
    assert second_window.current_folder_name == "chemistry"
    assert len(second_window.loaded_flashcards) == 1
    assert (
        second_window.timer_page.folder_context_label.text()
        == "Folder: chemistry (1 cards)"
    )


def test_multiple_checked_folders_aggregate_flashcards(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify checking multiple folders aggregates flashcards in timer scope."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    chemistry_folder = tmp_path / "chemistry"
    biology_folder.mkdir()
    chemistry_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "DNA?,Genetic material.\n", encoding="utf-8"
    )
    (chemistry_folder / "cards.csv").write_text("NaCl?,Salt.\n", encoding="utf-8")

    assert window.add_folder(biology_folder) is True
    assert window.add_folder(chemistry_folder) is True
    assert window.current_folder_name == "2 folders selected"
    assert len(window.loaded_flashcards) == 2

    first_item = window.sidebar_folder_list.item(0)
    first_item.setCheckState(Qt.Unchecked)
    assert len(window.loaded_flashcards) == 1


def test_sidebar_folder_context_actions_rename_and_delete(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify sidebar helpers rename and delete folders from context-menu actions."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "DNA?,Genetic material.\n", encoding="utf-8"
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)

    window.rename_sidebar_folder(folder_item)
    folder_item.setText("Biology Updated")
    renamed_item = window.sidebar_folder_list.item(0)
    assert renamed_item.text() == "Biology Updated"

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    window.delete_sidebar_folders([renamed_item])
    assert list_persisted_folders() == []


def test_start_timer_hides_navigation_until_stopped(app: QApplication) -> None:
    """Verify navigation controls hide during timer execution."""
    window = MainWindow()
    window.toggle_sidebar()

    window.timer_page.start_timer()
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()
    assert not window.sidebar.isVisible()

    window.timer_page.pause_timer()
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()

    window.timer_page.stop_timer()
    assert not window.sidebar_toggle_button.isHidden()
    assert not window.settings_button.isHidden()


def test_settings_save_returns_to_timer_page(app: QApplication) -> None:
    """Verify saving settings returns focus to timer page."""
    window = MainWindow()
    window.switch_to_settings()

    window.settings_page.save_button.click()

    assert window.stacked_widget.currentWidget() is window.timer_page


def test_timer_completion_without_trigger_restarts_cycle(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify completion restarts timer when probability roll does not trigger."""
    window = MainWindow()
    monkeypatch.setattr("estudai.ui.main_window.random.randint", lambda *_args: 100)

    window.handle_timer_cycle_completed()

    assert window.timer_page.is_running is True
    assert window.timer_page.timer_display.text() == "25:00"
    window.timer_page.stop_timer()


def test_timer_completion_with_trigger_and_no_folder_warns_and_restarts(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify triggered completion warns and restarts when no folder is selected."""
    window = MainWindow()
    warnings: list[str] = []
    monkeypatch.setattr("estudai.ui.main_window.random.randint", lambda *_args: 1)
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    window.handle_timer_cycle_completed()

    assert warnings
    assert window.timer_page.is_running is True
    window.timer_page.stop_timer()


def test_timer_completion_with_trigger_and_no_flashcards_warns_and_restarts(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify triggered completion warns and restarts when selected folders are empty."""
    window = MainWindow()
    empty_folder = tmp_path / "empty"
    empty_folder.mkdir()
    (empty_folder / "cards.csv").write_text("", encoding="utf-8")
    assert window.add_folder(empty_folder) is True
    warnings: list[str] = []
    monkeypatch.setattr("estudai.ui.main_window.random.randint", lambda *_args: 1)
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    window.handle_timer_cycle_completed()

    assert warnings
    assert window.timer_page.is_running is True
    window.timer_page.stop_timer()


def test_timer_completion_with_trigger_emits_flashcard_event(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify triggered completion emits show-flashcard event."""
    shown_flashcards: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.MainWindow.show_flashcard_popup",
        lambda self, flashcard: shown_flashcards.append(flashcard.question),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "DNA?,Genetic material.\n", encoding="utf-8"
    )
    assert window.add_folder(biology_folder) is True
    emitted_flashcards: list[object] = []
    warnings: list[str] = []
    window.show_flashcard_requested.connect(
        lambda flashcard: emitted_flashcards.append(flashcard)
    )
    monkeypatch.setattr("estudai.ui.main_window.random.randint", lambda *_args: 1)
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    window.handle_timer_cycle_completed()

    assert not warnings
    assert len(emitted_flashcards) == 1
    assert emitted_flashcards[0].question == "DNA?"
    assert shown_flashcards == ["DNA?"]


def test_timer_completion_uses_sequential_order_and_skips_consumption_on_miss(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify sequential order advances only when probability check triggers."""
    shown_flashcards: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.MainWindow.show_flashcard_popup",
        lambda self, flashcard: shown_flashcards.append(flashcard.question),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    rolls = iter([100, 1, 1])
    monkeypatch.setattr(
        "estudai.ui.main_window.random.randint", lambda *_args: next(rolls)
    )

    window.handle_timer_cycle_completed()
    assert shown_flashcards == []
    assert window._next_flashcard_index == 0

    window.handle_timer_cycle_completed()
    window.handle_timer_cycle_completed()

    assert shown_flashcards == ["Q1?", "Q2?"]
    assert window._next_flashcard_index == 0


def test_stop_button_resets_sequential_flashcard_order(
    app: QApplication,
) -> None:
    """Verify user stop action resets sequential flashcard pointer."""
    window = MainWindow()
    window._next_flashcard_index = 2
    window.timer_page.set_flashcard_controls_active(True)

    window.timer_page.stop_button.click()

    assert window._next_flashcard_index == 0


def test_timer_completion_uses_random_choice_when_setting_enabled(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify random-order setting uses random selection path."""
    shown_flashcards: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.MainWindow.show_flashcard_popup",
        lambda self, flashcard: shown_flashcards.append(flashcard.question),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=100,
            flashcard_random_order_enabled=True,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    monkeypatch.setattr("estudai.ui.main_window.random.randint", lambda *_args: 1)
    monkeypatch.setattr(
        "estudai.ui.main_window.random.choice", lambda flashcards: flashcards[-1]
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True

    window.handle_timer_cycle_completed()

    assert shown_flashcards == ["Q2?"]
    assert window._next_flashcard_index == 0


def test_flashcard_sequence_plays_sound_for_question_and_answer(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify flashcard flow plays notification sound at both phases."""
    sound_path = tmp_path / "alert.wav"
    sound_path.write_bytes(b"RIFF....WAVEfmt ")
    callbacks: list[object] = []
    source_values: list[str] = []
    plays: list[str] = []
    restart_calls: list[str] = []
    window = MainWindow()
    flashcard = Flashcard(
        question="Q?",
        answer="A.",
        source_file=tmp_path / "cards.csv",
        source_line=1,
    )

    class _FakePlayer:
        def setSource(self, url) -> None:  # noqa: N802
            source_values.append(url.toLocalFile())

        def play(self) -> None:
            plays.append("play")

    monkeypatch.setattr(window, "_flashcard_sound_player", _FakePlayer())

    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
            notification_sound_path=str(sound_path),
        ),
    )
    monkeypatch.setattr(
        window.timer_page,
        "restart_timer_cycle",
        lambda: restart_calls.append("restart"),
    )

    window.show_flashcard_popup(flashcard)
    assert window.timer_page.flashcard_question_label.text() == "Q?"
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()
    assert plays == ["play"]
    assert len(callbacks) == 1

    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "A."
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()
    assert plays == ["play", "play"]
    assert len(callbacks) == 1

    callbacks.pop(0)()
    assert restart_calls == ["restart"]


def test_flashcard_pause_handler_stops_and_resumes_phase_timer(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify flashcard pause toggles stop and resume on phase timer."""
    window = MainWindow()
    window.timer_page.show_flashcard_question("Q?", display_duration_seconds=5)
    window._pending_flashcard_phase_callback = lambda: None

    class _FakePhaseTimer:
        def __init__(self) -> None:
            self.active = True
            self.stopped = False
            self.started_with: int | None = None

        def isActive(self) -> bool:  # noqa: N802
            return self.active

        def remainingTime(self) -> int:  # noqa: N802
            return 1500

        def stop(self) -> None:
            self.stopped = True
            self.active = False

        def start(self, milliseconds: int) -> None:
            self.started_with = milliseconds
            self.active = True

    fake_timer = _FakePhaseTimer()
    monkeypatch.setattr(window, "_flashcard_phase_timer", fake_timer)

    window.handle_flashcard_pause_toggled(True)
    assert fake_timer.stopped is True
    assert window._flashcard_phase_remaining_ms == 1500

    window.handle_flashcard_pause_toggled(False)
    assert fake_timer.started_with == 1500


def test_create_folder_from_prompt(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify create-folder prompt adds a managed folder to sidebar."""
    window = MainWindow()
    monkeypatch.setattr(
        "estudai.ui.main_window.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Biology", True),
    )

    window.prompt_and_create_folder()

    assert window.sidebar_folder_list.count() == 1
    assert window.sidebar_folder_list.item(0).text() == "Biology"


def test_double_click_folder_opens_management_and_save_updates_selection(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify management page saves flashcards and selected card scope."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\nWhat is RNA?,Messenger molecule.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)

    window.handle_sidebar_folder_double_click(folder_item)
    assert window.stacked_widget.currentWidget() is window.management_page
    assert window.management_page.title_label.text() == "biology"

    table = window.management_page.flashcards_table
    assert table.rowCount() == 2
    table.item(0, 0).setCheckState(Qt.Unchecked)
    table.item(1, 2).setText("Updated messenger molecule.")

    window.save_management_changes()

    assert window.stacked_widget.currentWidget() is window.timer_page
    assert len(window.loaded_flashcards) == 1
    assert window.loaded_flashcards[0].question == "What is RNA?"
    assert window.loaded_flashcards[0].answer == "Updated messenger molecule."


def test_management_save_validates_non_empty_fields(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify management save warns and blocks save when fields are empty."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    warnings: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    window.management_page.flashcards_table.item(0, 1).setText(" ")
    window.save_management_changes()

    assert warnings
    assert window.stacked_widget.currentWidget() is window.management_page


def test_import_notebooklm_csv_appends_rows_to_selected_folder(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify NotebookLM import appends parsed rows into selected folder."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "What is DNA?,Genetic material.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_id = window.sidebar_folder_list.item(0).data(Qt.UserRole)

    class _FakeImportDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return QDialog.Accepted

        def selected_folder_id(self) -> str | None:
            return folder_id

        def import_rows(self) -> list[tuple[str, str]]:
            return [("Imported question?", "Imported answer.")]

    monkeypatch.setattr(
        "estudai.ui.main_window.NotebookLMCsvImportDialog",
        _FakeImportDialog,
    )

    window.prompt_and_import_notebooklm_csv()

    assert len(window.flashcards_by_folder[folder_id]) == 2
    assert window.flashcards_by_folder[folder_id][1].question == "Imported question?"
    assert window.loaded_flashcards[-1].answer == "Imported answer."
