"""Main window tests."""

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMessageBox,
    QPushButton,
    QStyleOptionViewItem,
)

from estudai.services.csv_flashcards import Flashcard
from estudai.services.folder_storage import list_persisted_folders
from estudai.services.hotkeys import GlobalHotkeyService, HotkeyRegistrationError
from estudai.services.settings import (
    AppSettings,
    WrongAnswerCompletionMode,
    WrongAnswerReinsertionMode,
    load_app_settings,
    save_app_settings,
)
from estudai.ui.main_window import MainWindow, SidebarCheckboxDelegate


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


class _FakeHotkeyBackend:
    """Minimal backend that lets UI tests trigger global hotkeys deterministically."""

    def __init__(self) -> None:
        self.active_handles: dict[str, tuple[str, object]] = {}
        self._next_handle = 0

    def register(self, binding: str, callback) -> object:
        handle = f"handle-{self._next_handle}"
        self._next_handle += 1
        self.active_handles[handle] = (binding, callback)
        return handle

    def unregister(self, handle: object) -> None:
        self.active_handles.pop(str(handle), None)

    def trigger(self, binding: str) -> None:
        for registered_binding, callback in self.active_handles.values():
            if registered_binding == binding:
                callback()
                return
        msg = f"No hotkey registered for {binding}"
        raise HotkeyRegistrationError(msg)


class _FullscreenSpyWindow(MainWindow):
    """Main window variant that records fullscreen method calls for tests."""

    def __init__(self) -> None:
        self.fullscreen_state = False
        self.fullscreen_calls: list[str] = []
        self.toggle_fullscreen_call_count = 0
        self.exit_fullscreen_call_count = 0
        super().__init__()

    def isFullScreen(self) -> bool:  # noqa: N802
        """Return the test-controlled fullscreen state."""
        return self.fullscreen_state

    def showFullScreen(self) -> None:  # noqa: N802
        """Record fullscreen entry without needing a real window manager."""
        self.fullscreen_calls.append("showFullScreen")
        self.fullscreen_state = True

    def showNormal(self) -> None:  # noqa: N802
        """Record fullscreen exit without needing a real window manager."""
        self.fullscreen_calls.append("showNormal")
        self.fullscreen_state = False

    def toggle_fullscreen(self) -> None:
        """Record shortcut activation and delegate to the real logic."""
        self.toggle_fullscreen_call_count += 1
        super().toggle_fullscreen()

    def exit_fullscreen(self) -> None:
        """Record shortcut activation and delegate to the real logic."""
        self.exit_fullscreen_call_count += 1
        super().exit_fullscreen()


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


def test_sidebar_toggle_button_stays_in_place(app: QApplication) -> None:
    """Verify sidebar toggle/content positions stay stable when sidebar opens."""
    window = MainWindow()
    toggle_position_before = window.sidebar_toggle_button.mapTo(window, QPoint(0, 0))
    content_x_before = window.stacked_widget.mapTo(window, QPoint(0, 0)).x()
    window.toggle_sidebar()
    toggle_position_open = window.sidebar_toggle_button.mapTo(window, QPoint(0, 0))
    content_x_open = window.stacked_widget.mapTo(window, QPoint(0, 0)).x()

    assert window.sidebar_toggle_button.parent() is window.header_container
    assert content_x_before == content_x_open == 0
    assert toggle_position_before == toggle_position_open


def test_top_navigation_buttons_are_larger(app: QApplication) -> None:
    """Verify top sidebar/config buttons use larger fixed sizes."""
    window = MainWindow()

    assert window.sidebar_toggle_button.width() == 44
    assert window.settings_button.width() == 44


def test_sidebar_uses_delegate_checkbox_rendering(
    app: QApplication,
) -> None:
    """Verify sidebar uses native checkbox delegate rendering with stable style hints."""
    window = MainWindow()

    stylesheet = window.sidebar_folder_list.styleSheet()

    assert isinstance(
        window.sidebar_folder_list.itemDelegate(), SidebarCheckboxDelegate
    )
    assert "show-decoration-selected: 0;" in stylesheet
    assert "QListWidget::indicator" not in stylesheet


def test_sidebar_checkbox_delegate_toggles_checkbox_on_indicator_click(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify sidebar checkbox delegate toggles folder checks from indicator clicks."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("What is DNA?,Genetic material.\n")
    assert window.add_folder(biology_folder) is True

    folder_item = window.sidebar_folder_list.item(0)
    model = window.sidebar_folder_list.model()
    index = model.index(0, 0)
    delegate = window.sidebar_folder_list.itemDelegate()
    option = QStyleOptionViewItem()
    option.widget = window.sidebar_folder_list
    option.rect = QRect(0, 0, 260, 28)
    click_position = QPointF(12, 14)

    press_event = QMouseEvent(
        QEvent.MouseButtonPress,
        click_position,
        click_position,
        click_position,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    release_event = QMouseEvent(
        QEvent.MouseButtonRelease,
        click_position,
        click_position,
        click_position,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    assert folder_item.checkState() == Qt.Checked
    assert delegate.editorEvent(press_event, model, option, index) is True
    assert delegate.editorEvent(release_event, model, option, index) is True
    assert folder_item.checkState() == Qt.Unchecked


def test_primary_button_tooltips_are_short(app: QApplication) -> None:
    """Verify key control tooltips use concise labels."""
    window = MainWindow()

    assert window.sidebar_toggle_button.toolTip() == "Toggle folders sidebar"
    assert window.settings_button.toolTip() == "Open settings"
    assert window.sidebar_toggle_button.text() == ""
    assert window.settings_button.text() == ""
    assert not window.sidebar_toggle_button.icon().isNull()
    assert not window.settings_button.icon().isNull()
    assert window.timer_page.start_button.toolTip() == "Start"
    assert window.timer_page.pause_button.toolTip() == "Pause"
    assert window.timer_page.stop_button.toolTip() == "Stop"


def test_sidebar_width_is_capped_for_large_windows(app: QApplication) -> None:
    """Verify sidebar width stays capped on wide displays."""
    window = MainWindow()
    window.resize(3000, 1200)
    window._update_sidebar_width()

    assert window.sidebar.width() == 300


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
    """Verify sidebar keeps reorder controls above create/import actions."""
    window = MainWindow()
    sidebar_layout = window.sidebar.layout()
    reorder_layout = sidebar_layout.itemAt(2).layout()
    assert reorder_layout is not None
    reorder_button_texts = [
        reorder_layout.itemAt(index).widget().text()
        for index in range(reorder_layout.count())
        if isinstance(reorder_layout.itemAt(index).widget(), QPushButton)
    ]
    action_button_texts = [
        sidebar_layout.itemAt(index).widget().text()
        for index in range(sidebar_layout.count())
        if isinstance(sidebar_layout.itemAt(index).widget(), QPushButton)
    ]

    assert reorder_button_texts == [
        "Move Up",
        "Move Down",
    ]
    assert action_button_texts == [
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


def test_checked_sidebar_folder_is_rendered_bold(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify checked folders have a clear visual cue in the sidebar."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("What is DNA?,Genetic material.\n")
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)

    assert folder_item.checkState() == Qt.Checked
    assert folder_item.font().bold() is True

    folder_item.setCheckState(Qt.Unchecked)

    assert folder_item.font().bold() is False


def test_palette_change_reapplies_sidebar_item_visuals(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify palette changes trigger sidebar checked-state visual recomputation."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("What is DNA?,Genetic material.\n")
    assert window.add_folder(biology_folder) is True
    calls: list[str] = []

    monkeypatch.setattr(
        window,
        "_refresh_sidebar_item_visual_states",
        lambda: calls.append("refresh"),
    )

    window.changeEvent(QEvent(QEvent.PaletteChange))

    assert calls == ["refresh"]


def test_palette_change_reapplies_sidebar_palette_styles(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify palette changes reapply sidebar frame/list palette styles."""
    window = MainWindow()
    calls: list[str] = []

    monkeypatch.setattr(
        window,
        "_apply_sidebar_palette_styles",
        lambda: calls.append("styles"),
    )

    window.changeEvent(QEvent(QEvent.ApplicationPaletteChange))

    assert calls == ["styles"]


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
    assert window.sidebar_folder_list.item(0).text() == "biology (2 cards)"
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
        == "Folder: chemistry (1 card)"
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
    assert renamed_item.text() == "Biology Updated (1 card)"

    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.Yes,
    )
    window.delete_sidebar_folders([renamed_item])
    assert list_persisted_folders() == []


def test_management_sort_persists_flashcard_order_and_selected_cards(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify A-Z sorting persists and keeps the same cards selected."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "beta?,B.\ngamma?,G.\nAlpha?,A.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)
    folder_id = folder_item.data(Qt.UserRole)
    assert isinstance(folder_id, str)

    window.open_management_for_folder(folder_id, "biology")
    window.management_page.flashcards_table.item(1, 0).setCheckState(Qt.Unchecked)
    window.management_page.sort_flashcards_by_question()
    window.save_management_changes()

    assert [card.question for card in window.flashcards_by_folder[folder_id]] == [
        "Alpha?",
        "beta?",
        "gamma?",
    ]
    assert [card.question for card in window.loaded_flashcards] == [
        "Alpha?",
        "beta?",
    ]

    reloaded_window = MainWindow()
    reloaded_folder_id = next(iter(reloaded_window.flashcards_by_folder))
    assert [
        card.question
        for card in reloaded_window.flashcards_by_folder[reloaded_folder_id]
    ] == [
        "Alpha?",
        "beta?",
        "gamma?",
    ]


def test_management_reorder_keeps_checked_state_with_flashcard(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify manual flashcard moves keep the checked cards attached to the rows."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "First?,A.\nSecond?,B.\nThird?,C.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)
    folder_id = folder_item.data(Qt.UserRole)
    assert isinstance(folder_id, str)

    window.open_management_for_folder(folder_id, "biology")
    window.management_page.flashcards_table.item(1, 0).setCheckState(Qt.Unchecked)
    window.management_page.flashcards_table.selectRow(2)
    window.management_page.move_selected_rows_up()
    window.save_management_changes()

    assert [card.question for card in window.flashcards_by_folder[folder_id]] == [
        "First?",
        "Third?",
        "Second?",
    ]
    assert [card.question for card in window.loaded_flashcards] == [
        "First?",
        "Third?",
    ]


def test_sidebar_folder_reorder_persists_and_preserves_checked_ids(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify sidebar folder moves persist and keep folder selection intact."""
    window = MainWindow()
    for name in ("biology", "chemistry", "physics"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "cards.csv").write_text(f"{name}?,A.\n", encoding="utf-8")
        assert window.add_folder(folder) is True

    chemistry_item = window.sidebar_folder_list.item(1)
    window.sidebar_folder_list.clearSelection()
    chemistry_item.setSelected(True)
    window.sidebar_folder_list.setCurrentItem(chemistry_item)

    window.move_selected_sidebar_folder_up()

    assert [
        window.sidebar_folder_list.item(index).data(window.FOLDER_NAME_ROLE)
        for index in range(window.sidebar_folder_list.count())
    ] == ["chemistry", "biology", "physics"]
    assert window._get_checked_folder_ids() == set(window.flashcards_by_folder)

    reloaded_window = MainWindow()
    assert [
        reloaded_window.sidebar_folder_list.item(index).data(window.FOLDER_NAME_ROLE)
        for index in range(reloaded_window.sidebar_folder_list.count())
    ] == ["chemistry", "biology", "physics"]


def test_start_timer_hides_navigation_until_stopped(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify navigation controls hide during timer execution."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.toggle_sidebar()

    window.timer_page.start_timer()
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()
    assert not window.sidebar.isVisible()

    window.timer_page.pause_timer()
    assert window.sidebar_toggle_button.isHidden()
    assert window.settings_button.isHidden()

    window.timer_page.stop_button.click()
    assert not window.sidebar_toggle_button.isHidden()
    assert not window.settings_button.isHidden()


def test_settings_save_returns_to_timer_page(app: QApplication) -> None:
    """Verify saving settings returns focus to timer page."""
    window = MainWindow()
    window.switch_to_settings()

    window.settings_page.save_button.click()

    assert window.stacked_widget.currentWidget() is window.timer_page


def test_start_timer_without_selected_folders_warns_and_stops(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify starting without checked flashcards keeps the app in a safe idle state."""
    window = MainWindow()
    warnings: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args: warnings.append("warning"),
    )

    window.timer_page.start_timer()

    assert warnings == ["warning"]
    assert window.timer_page.is_running is False
    assert window._study_session.active is False
    assert "completed" not in window.timer_page.folder_context_label.text()


def test_start_timer_with_selected_flashcards_starts_study_session(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify pressing Start initializes one scored study session snapshot."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True

    window.timer_page.start_timer()

    assert window._study_session.active is True
    assert "0/2 completed | 2 remaining | 0 pending review" in (
        window.timer_page.folder_context_label.text()
    )
    window.timer_page.stop_button.click()


def test_zero_second_timer_starts_flashcards_immediately_and_resets_to_ready(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify instant mode skips countdown and restores Ready? after stopping."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=0,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )

    assert window.timer_page.timer_display.text() == "Ready?"

    window.timer_page.start_timer()

    assert window._study_session.active is True
    assert window.timer_page.is_running is False
    assert window.timer_page.flashcard_question_label.text() == "Q1?"
    assert len(callbacks) == 1

    window.timer_page.stop_button.click()

    assert window._study_session.active is False
    assert window.timer_page.timer_display.text() == "Ready?"


def test_scored_session_marks_wrong_then_correct_until_complete(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify answer selections apply only when the answer timer finishes."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )
    window.timer_page.start_timer()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q1?"
    assert len(callbacks) == 1
    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "A1."
    assert window._study_session.current_flashcard_index == 0
    window.timer_page.wrong_button.click()
    assert window._pending_flashcard_score == "wrong"
    assert window._study_session.card_states[0].value == "pending"
    callbacks.pop(0)()
    assert window._study_session.card_states[0].value == "wrong_pending"
    assert "0/2 completed | 2 remaining | 1 pending review" in (
        window.timer_page.folder_context_label.text()
    )
    assert window.timer_page.is_running is True

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q2?"
    assert len(callbacks) == 1
    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "A2."
    assert window._study_session.current_flashcard_index == 1
    window.timer_page.correct_button.click()
    assert window._pending_flashcard_score == "correct"
    assert window._study_session.card_states[1].value == "pending"
    callbacks.pop(0)()
    assert window._study_session.card_states[1].value == "completed"
    assert "1/2 completed | 1 remaining | 1 pending review" in (
        window.timer_page.folder_context_label.text()
    )
    assert window.timer_page.is_running is True

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q1?"
    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "A1."
    window.timer_page.correct_button.click()
    callbacks.pop(0)()

    assert window._study_session.active is False
    assert window.timer_page.is_running is False
    assert window.timer_page.flashcard_question_label.isHidden()
    assert "completed" not in window.timer_page.folder_context_label.text()


def test_scored_session_mode_b_requires_more_correct_than_wrong_end_to_end(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify Mode B keeps a card active until correct answers exceed wrong answers."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
            wrong_answer_completion_mode=(
                WrongAnswerCompletionMode.UNTIL_CORRECT_MORE_THAN_WRONG
            ),
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )
    window.timer_page.start_timer()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    callbacks.pop(0)()
    window.timer_page.wrong_button.click()
    callbacks.pop(0)()
    assert window._study_session.card_states[0].value == "wrong_pending"
    assert window._study_session.card_counters[0].wrong_count == 1

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    callbacks.pop(0)()
    window.timer_page.correct_button.click()
    callbacks.pop(0)()
    assert window._study_session.card_states[0].value == "wrong_pending"
    assert window._study_session.card_counters[0].correct_count == 1
    assert window._study_session.active is True

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    callbacks.pop(0)()
    window.timer_page.correct_button.click()
    callbacks.pop(0)()

    assert window._study_session.active is False
    assert window.timer_page.is_running is False


def test_wrong_answer_after_x_reinsertion_returns_card_after_requested_gap(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify After-X reinsertion changes the next-card order in the UI flow."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
            wrong_answer_reinsertion_mode=(
                WrongAnswerReinsertionMode.AFTER_X_FLASHCARDS
            ),
            wrong_answer_reinsert_after_count=1,
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\nQ3?,A3.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )
    window.timer_page.start_timer()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q1?"
    callbacks.pop(0)()
    window.timer_page.wrong_button.click()
    callbacks.pop(0)()
    assert window._study_session.queued_flashcard_indexes() == [1, 0, 2]

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q2?"
    callbacks.pop(0)()
    window.timer_page.correct_button.click()
    callbacks.pop(0)()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q1?"


def test_stop_button_resets_runtime_study_session_state(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify Stop clears session progress and order instead of leaving runtime state behind."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.timer_page.start_timer()
    window._next_flashcard_index = 2

    window.timer_page.stop_button.click()

    assert window._study_session.active is False
    assert window._next_flashcard_index == 0
    assert "completed" not in window.timer_page.folder_context_label.text()
    assert window.timer_page.start_button.isEnabled()


def test_timer_completion_uses_random_choice_when_setting_enabled(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify session selection uses the random-order path when configured."""
    shown_flashcards: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.MainWindow.show_flashcard_popup",
        lambda self, flashcard: shown_flashcards.append(flashcard.question),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=True,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
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
    window.timer_page.start_timer()
    window.timer_page.is_running = False

    window.handle_timer_cycle_completed()

    assert shown_flashcards == ["Q2?"]
    assert window._study_session.current_flashcard_index == 1


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

    window.timer_page.correct_button.click()
    assert window.timer_page.correct_button.isChecked()
    assert restart_calls == []
    callbacks.pop(0)()
    assert restart_calls == ["restart"]


def test_unanswered_flashcard_returns_after_other_cards(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify unanswered cards stay pending and move behind later cards."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )
    window.timer_page.start_timer()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "A1."
    callbacks.pop(0)()
    assert window._study_session.card_states[0].value == "pending"
    assert window.timer_page.is_running is True

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    assert window.timer_page.flashcard_question_label.text() == "Q2?"


def test_paused_flashcard_edit_updates_current_display_and_future_retry(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify paused editing persists immediately and updates later retries too."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    folder_id = window.sidebar_folder_list.item(0).data(Qt.UserRole)

    class _FakeEditDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return QDialog.Accepted

        def question_text(self) -> str:
            return "Edited Q1?"

        def answer_text(self) -> str:
            return "Edited A1."

    monkeypatch.setattr(
        "estudai.ui.main_window.FlashcardEditDialog",
        _FakeEditDialog,
    )
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )

    window.timer_page.start_timer()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    window.timer_page.pause_timer()
    window.timer_page.edit_flashcard_button.click()

    assert window.timer_page.flashcard_question_label.text() == "Edited Q1?"
    assert window.flashcards_by_folder[folder_id][0].question == "Edited Q1?"
    assert window.flashcards_by_folder[folder_id][0].answer == "Edited A1."

    callbacks.pop(0)()
    assert window.timer_page.flashcard_answer_label.text() == "Edited A1."

    window.timer_page.wrong_button.click()
    callbacks.pop(0)()

    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()

    assert window.timer_page.flashcard_question_label.text() == "Edited Q1?"


def test_paused_flashcard_delete_removes_card_from_active_session(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify deleting the paused card removes it from storage and future session flow."""
    callbacks: list[object] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    folder_id = window.sidebar_folder_list.item(0).data(Qt.UserRole)
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )

    window.timer_page.start_timer()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    window.timer_page.pause_timer()
    window.timer_page.delete_flashcard_button.click()

    assert [card.question for card in window.flashcards_by_folder[folder_id]] == ["Q2?"]
    assert window._study_session.current_flashcard() is None
    assert window._study_session.queued_flashcard_indexes() == [0]
    assert window.timer_page.pause_button.text() == "Resume"
    assert window.timer_page.flashcard_question_label.isHidden()

    window.timer_page.pause_button.click()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()

    assert window.timer_page.flashcard_question_label.text() == "Q2?"
    assert window.timer_page.flashcard_question_label.text() != "Q1?"


def test_deleting_last_paused_flashcard_completes_session_cleanly(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify deleting the final pending flashcard completes the session safely."""
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: None,
    )

    window.timer_page.start_timer()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    window.timer_page.pause_timer()
    window.timer_page.delete_flashcard_button.click()

    assert window._study_session.active is False
    assert window.timer_page.start_button.isEnabled()
    assert not window.timer_page.pause_button.isEnabled()
    assert not window.timer_page.stop_button.isEnabled()
    assert window.timer_page.flashcard_question_label.isHidden()
    assert window.loaded_flashcards == []


def test_paused_flashcard_delete_keeps_next_card_editable(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify deleting one paused card does not break editing later cards in that folder."""
    callbacks: list[object] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.main_window.load_app_settings",
        lambda: AppSettings(
            timer_duration_seconds=1500,
            flashcard_probability_percent=30,
            flashcard_random_order_enabled=False,
            question_display_duration_seconds=2,
            answer_display_duration_seconds=3,
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.warning",
        lambda *_args, **_kwargs: warnings.append("warning"),
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\nQ3?,A3.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_id = window.sidebar_folder_list.item(0).data(Qt.UserRole)

    class _FakeEditDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self) -> int:
            return QDialog.Accepted

        def question_text(self) -> str:
            return "Edited Q2?"

        def answer_text(self) -> str:
            return "Edited A2."

    monkeypatch.setattr(
        "estudai.ui.main_window.FlashcardEditDialog",
        _FakeEditDialog,
    )
    monkeypatch.setattr(
        window,
        "_start_flashcard_phase_timer",
        lambda _delay, callback: callbacks.append(callback),
    )

    window.timer_page.start_timer()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    window.timer_page.pause_timer()
    window.timer_page.delete_flashcard_button.click()

    window.timer_page.pause_button.click()
    window.timer_page.is_running = False
    window.handle_timer_cycle_completed()
    window.timer_page.pause_timer()
    window.timer_page.edit_flashcard_button.click()

    assert warnings == []
    assert window.timer_page.flashcard_question_label.text() == "Edited Q2?"
    assert [card.question for card in window.flashcards_by_folder[folder_id]] == [
        "Edited Q2?",
        "Q3?",
    ]


def test_flashcard_pause_handler_stops_and_resumes_phase_timer(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify pause/resume preserves live session state during a flashcard phase."""
    window = MainWindow()
    window._study_session.start(
        [
            Flashcard(
                question="Q?",
                answer="A.",
                source_file=Path("cards.csv"),
                source_line=1,
            )
        ],
        wrong_answer_completion_mode=WrongAnswerCompletionMode.UNTIL_CORRECT_ONCE,
        wrong_answer_reinsertion_mode=WrongAnswerReinsertionMode.PUSH_TO_END,
        wrong_answer_reinsert_after_count=3,
        random_order=False,
        choice_func=lambda indexes: indexes[0],
    )
    window._study_session.set_current_flashcard(0)
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
    assert window._study_session.current_flashcard_index == 0

    window.handle_flashcard_pause_toggled(False)
    assert fake_timer.started_with == 1500
    assert window._study_session.card_states[0].value == "pending"


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
    assert window.sidebar_folder_list.item(0).text() == "Biology (0 cards)"


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
    assert window.sidebar.isHidden()
    assert not window.sidebar_toggle_button.isHidden()

    table = window.management_page.flashcards_table
    assert table.rowCount() == 2
    table.item(0, 0).setCheckState(Qt.Unchecked)
    table.item(1, 2).setText("Updated messenger molecule.")
    window.toggle_sidebar()
    assert not window.sidebar.isHidden()
    window.toggle_sidebar()
    assert window.sidebar.isHidden()

    window.save_management_changes()

    assert window.stacked_widget.currentWidget() is window.timer_page
    assert len(window.loaded_flashcards) == 1
    assert window.loaded_flashcards[0].question == "What is RNA?"
    assert window.loaded_flashcards[0].answer == "Updated messenger molecule."


def test_management_select_and_unselect_all_controls(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify first-column header toggles all flashcard checkboxes."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    table = window.management_page.flashcards_table
    table.item(0, 0).setCheckState(Qt.Unchecked)
    table.item(1, 0).setCheckState(Qt.Checked)

    assert window.management_page.is_header_checkbox_checked() is False
    window.management_page.handle_table_header_click(0)
    assert table.item(0, 0).checkState() == Qt.Checked
    assert table.item(1, 0).checkState() == Qt.Checked
    assert window.management_page.is_header_checkbox_checked() is True

    window.management_page.handle_table_header_click(0)
    assert table.item(0, 0).checkState() == Qt.Unchecked
    assert table.item(1, 0).checkState() == Qt.Unchecked
    assert window.management_page.is_header_checkbox_checked() is False


def test_management_add_button_is_plus_at_top(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify the management action bar exposes reorder, sort, and add controls."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    table = window.management_page.flashcards_table
    management_layout = window.management_page.layout()
    action_layout = management_layout.itemAt(2).layout()
    assert action_layout is not None
    action_button_texts = [
        action_layout.itemAt(index).widget().text()
        for index in range(action_layout.count())
        if isinstance(action_layout.itemAt(index).widget(), QPushButton)
    ]

    assert window.management_page.add_flashcard_button.text() == "+"
    assert action_button_texts == [
        "Move Up",
        "Move Down",
        "Sort by Question A-Z",
        "+",
    ]
    assert management_layout.itemAt(3).widget() is table
    window.management_page.add_flashcard_button.click()
    assert table.rowCount() == 2


def test_management_table_keeps_native_checkbox_indicator_styles(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify management table does not override native checkbox indicator styles."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    stylesheet = window.management_page.flashcards_table.styleSheet()

    assert stylesheet == ""


def test_management_header_checkbox_only_toggles_on_indicator_click(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify header select-all ignores clicks outside the painted checkbox."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    table = window.management_page.flashcards_table
    header = window.management_page.select_all_header
    table.setColumnWidth(0, 60)
    table.item(0, 0).setCheckState(Qt.Unchecked)
    table.item(1, 0).setCheckState(Qt.Checked)

    click_position = QPointF(52, header.height() / 2)
    release_event = QMouseEvent(
        QEvent.MouseButtonRelease,
        click_position,
        click_position,
        click_position,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    header.mouseReleaseEvent(release_event)

    assert table.item(0, 0).checkState() == Qt.Unchecked
    assert table.item(1, 0).checkState() == Qt.Checked


def test_management_checkbox_delegate_ignores_clicks_outside_indicator(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify table checkbox delegate only reacts to clicks on the indicator."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    table = window.management_page.flashcards_table
    model = table.model()
    index = model.index(0, 0)
    delegate = table.itemDelegateForColumn(0)
    option = QStyleOptionViewItem()
    option.widget = table
    option.rect = QRect(0, 0, 60, 28)
    click_position = QPointF(50, 14)

    press_event = QMouseEvent(
        QEvent.MouseButtonPress,
        click_position,
        click_position,
        click_position,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    release_event = QMouseEvent(
        QEvent.MouseButtonRelease,
        click_position,
        click_position,
        click_position,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )

    assert table.item(0, 0).checkState() == Qt.Checked
    assert delegate.editorEvent(press_event, model, option, index) is False
    assert delegate.editorEvent(release_event, model, option, index) is False
    assert table.item(0, 0).checkState() == Qt.Checked


def test_management_right_click_delete_selected_rows(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify right-click delete action removes selected flashcards."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\nQ2?,A2.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    window.handle_sidebar_folder_double_click(window.sidebar_folder_list.item(0))
    table = window.management_page.flashcards_table
    table.selectRow(0)

    class _FakeMenu:
        def __init__(self, *_args, **_kwargs) -> None:
            self.actions = []

        def addAction(self, text: str):  # noqa: N802
            action = object()
            self.actions.append(action)
            return action

        def exec(self, *_args, **_kwargs):  # noqa: A003
            return self.actions[0]

    monkeypatch.setattr("estudai.ui.pages.management_page.QMenu", _FakeMenu)
    monkeypatch.setattr(
        "estudai.ui.main_window.QMessageBox.question",
        lambda *_args, **_kwargs: QMessageBox.Yes,
    )
    monkeypatch.setattr(table, "itemAt", lambda _pos: table.item(0, 1))

    window.management_page.open_flashcards_table_menu(QPoint(0, 0))

    assert table.rowCount() == 1
    assert table.item(0, 1).text() == "Q2?"


def test_management_save_auto_checks_folder_when_flashcard_selected(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify saving selected flashcards re-checks the edited folder."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)
    folder_item.setCheckState(Qt.Unchecked)
    window.handle_sidebar_folder_double_click(folder_item)
    table = window.management_page.flashcards_table
    table.item(0, 0).setCheckState(Qt.Checked)
    table.item(1, 0).setCheckState(Qt.Unchecked)

    window.save_management_changes()

    updated_item = window.sidebar_folder_list.item(0)
    assert updated_item.checkState() == Qt.Checked
    assert window.current_folder_name == "biology"
    assert len(window.loaded_flashcards) == 1


def test_management_save_unchecks_folder_when_no_flashcards_selected(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify saving with all rows unchecked unchecks the edited folder."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text(
        "Q1?,A1.\nQ2?,A2.\n",
        encoding="utf-8",
    )
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)
    window.handle_sidebar_folder_double_click(folder_item)
    table = window.management_page.flashcards_table
    table.item(0, 0).setCheckState(Qt.Unchecked)
    table.item(1, 0).setCheckState(Qt.Unchecked)

    window.save_management_changes()

    updated_item = window.sidebar_folder_list.item(0)
    assert updated_item.checkState() == Qt.Unchecked
    assert window.current_folder_name == "No folders selected"
    assert len(window.loaded_flashcards) == 0


def test_sidebar_click_does_not_leave_management_page(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify clicking sidebar folder does not force timer navigation."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    folder_item = window.sidebar_folder_list.item(0)
    window.handle_sidebar_folder_double_click(folder_item)

    window.handle_sidebar_folder_click(folder_item)

    assert window.stacked_widget.currentWidget() is window.management_page


def test_in_app_timer_shortcuts_control_timer(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify in-app timer shortcuts mirror the timer button flows."""
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True

    assert window._timer_page_pause_resume_shortcut.context() == Qt.ApplicationShortcut
    assert window._timer_page_pause_resume_shortcut.key().toString() == "Space"
    assert len(window._timer_page_start_stop_shortcuts) == 2
    assert {
        shortcut.key().toString()
        for shortcut in window._timer_page_start_stop_shortcuts
    } == {"Return", "Enter"}
    assert window._timer_page_mark_correct_shortcut.context() == Qt.ApplicationShortcut
    assert window._timer_page_mark_correct_shortcut.key().toString() == "Up"
    assert window._timer_page_mark_wrong_shortcut.context() == Qt.ApplicationShortcut
    assert window._timer_page_mark_wrong_shortcut.key().toString() == "Down"

    window._timer_page_start_stop_shortcuts[0].activated.emit()
    assert window.timer_page.is_running is True

    window._timer_page_pause_resume_shortcut.activated.emit()
    assert window.timer_page.is_running is False

    window._timer_page_pause_resume_shortcut.activated.emit()
    assert window.timer_page.is_running is True

    window._timer_page_start_stop_shortcuts[1].activated.emit()
    assert window.timer_page.is_running is False
    assert window.timer_page.start_button.isEnabled() is True
    assert window.timer_page.stop_button.isEnabled() is False


def test_modified_global_binding_does_not_trigger_local_space_shortcut(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify Ctrl+Alt+Space only follows the global pause path inside the app."""
    backend = _FakeHotkeyBackend()
    window = MainWindow(hotkey_service=GlobalHotkeyService(backend=backend))
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True

    window._timer_page_start_stop_shortcuts[0].activated.emit()
    assert window.timer_page.is_running is True

    modified_space_event = QKeyEvent(
        QEvent.KeyPress,
        Qt.Key_Space,
        Qt.ControlModifier | Qt.AltModifier,
    )
    QApplication.sendEvent(window, modified_space_event)
    assert window.timer_page.is_running is True

    backend.trigger("ctrl+alt+space")
    assert window.timer_page.is_running is False
    assert window.timer_page.pause_button.text() == "Resume"


def test_fullscreen_shortcuts_use_app_scope_and_expected_handlers(
    app: QApplication,
) -> None:
    """Verify F11 toggles fullscreen and Escape exits it through shortcuts."""
    window = _FullscreenSpyWindow()

    assert window._toggle_fullscreen_shortcut.context() == Qt.ApplicationShortcut
    assert window._toggle_fullscreen_shortcut.key().toString() == "F11"
    assert window._exit_fullscreen_shortcut.context() == Qt.ApplicationShortcut
    assert window._exit_fullscreen_shortcut.key().toString() == "Esc"

    window._toggle_fullscreen_shortcut.activated.emit()
    window._exit_fullscreen_shortcut.activated.emit()

    assert window.toggle_fullscreen_call_count == 1
    assert window.exit_fullscreen_call_count == 1
    assert window.fullscreen_calls == ["showFullScreen", "showNormal"]


def test_toggle_fullscreen_switches_between_fullscreen_and_normal_modes(
    app: QApplication,
) -> None:
    """Verify fullscreen helper enters and leaves fullscreen deterministically."""
    window = _FullscreenSpyWindow()

    window.toggle_fullscreen()
    window.toggle_fullscreen()
    window.exit_fullscreen()

    assert window.fullscreen_calls == ["showFullScreen", "showNormal"]
    assert window.isFullScreen() is False


def test_global_hotkeys_control_timer_using_button_paths(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify global start/stop and pause/resume actions mirror timer buttons."""
    backend = _FakeHotkeyBackend()
    window = MainWindow(hotkey_service=GlobalHotkeyService(backend=backend))
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True

    backend.trigger("ctrl+alt+enter")
    assert window.timer_page.is_running is True

    backend.trigger("ctrl+alt+space")
    assert window.timer_page.is_running is False
    assert window.timer_page.pause_button.text() == "Resume"

    backend.trigger("ctrl+alt+enter")
    assert window.timer_page.is_running is False
    assert window.timer_page.start_button.isEnabled() is True
    assert window.timer_page.stop_button.isEnabled() is False


def test_global_hotkeys_score_flashcards_through_existing_controls(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify scoring hotkeys drive the same selected-state flow as the score buttons."""
    save_app_settings(
        AppSettings(
            question_display_duration_seconds=1,
            answer_display_duration_seconds=8,
        )
    )
    backend = _FakeHotkeyBackend()
    window = MainWindow(hotkey_service=GlobalHotkeyService(backend=backend))
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    assert window._start_study_session() is True

    flashcard = window._next_flashcard_for_display()
    assert flashcard is not None
    window.show_flashcard_popup(flashcard)
    window._show_current_flashcard_answer(window._active_flashcard_sequence_id, 8)

    backend.trigger("ctrl+alt+up")
    assert window.timer_page.selected_flashcard_score() == "correct"
    assert window._pending_flashcard_score == "correct"

    backend.trigger("ctrl+alt+down")
    assert window.timer_page.selected_flashcard_score() == "wrong"
    assert window._pending_flashcard_score == "wrong"


def test_in_app_hotkeys_score_flashcards_through_existing_controls(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify local Up and Down shortcuts mirror the flashcard score buttons."""
    save_app_settings(
        AppSettings(
            question_display_duration_seconds=1,
            answer_display_duration_seconds=8,
        )
    )
    window = MainWindow()
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True
    assert window._start_study_session() is True

    flashcard = window._next_flashcard_for_display()
    assert flashcard is not None
    window.show_flashcard_popup(flashcard)
    window._show_current_flashcard_answer(window._active_flashcard_sequence_id, 8)

    window._timer_page_mark_correct_shortcut.activated.emit()
    assert window.timer_page.selected_flashcard_score() == "correct"
    assert window._pending_flashcard_score == "correct"

    window._timer_page_mark_wrong_shortcut.activated.emit()
    assert window.timer_page.selected_flashcard_score() == "wrong"
    assert window._pending_flashcard_score == "wrong"


def test_saving_settings_rebinds_active_global_hotkeys(
    app: QApplication, tmp_path: Path
) -> None:
    """Verify saving new bindings updates the active global registration set."""
    backend = _FakeHotkeyBackend()
    window = MainWindow(hotkey_service=GlobalHotkeyService(backend=backend))
    biology_folder = tmp_path / "biology"
    biology_folder.mkdir()
    (biology_folder / "cards.csv").write_text("Q1?,A1.\n", encoding="utf-8")
    assert window.add_folder(biology_folder) is True

    window.switch_to_settings()
    window.settings_page.start_stop_hotkey_edit.setKeySequence("Ctrl+Alt+S")
    window.settings_page.pause_resume_hotkey_edit.setKeySequence("Ctrl+Alt+P")
    window.settings_page.mark_correct_hotkey_edit.setKeySequence("Ctrl+Alt+Right")
    window.settings_page.mark_wrong_hotkey_edit.setKeySequence("Ctrl+Alt+Left")

    window.settings_page._handle_save_clicked()

    persisted = load_app_settings()
    assert persisted.start_stop_hotkey == "Ctrl+Alt+S"
    assert persisted.pause_resume_hotkey == "Ctrl+Alt+P"
    assert persisted.mark_correct_hotkey == "Ctrl+Alt+Right"
    assert persisted.mark_wrong_hotkey == "Ctrl+Alt+Left"

    backend.trigger("ctrl+alt+s")
    assert window.timer_page.is_running is True


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
