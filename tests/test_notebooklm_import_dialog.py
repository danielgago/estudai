"""NotebookLM import dialog tests."""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from estudai.services.folder_storage import create_managed_folder
from estudai.ui.dialog.notebooklm_import_dialog import NotebookLMCsvImportDialog

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


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


def test_dialog_initial_state_without_folders(app: QApplication) -> None:
    """Verify dialog starts disabled when no target folder is available."""
    dialog = NotebookLMCsvImportDialog()

    assert dialog.target_folder_combo.count() == 1
    assert dialog.selected_folder_id() is None
    assert dialog.import_rows() == []
    assert not dialog.import_button.isEnabled()


def test_choose_csv_file_populates_preview_and_enables_import(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify selecting CSV populates preview and enables import."""
    create_managed_folder("Biology")
    csv_path = tmp_path / "notebooklm.csv"
    csv_path.write_text(
        "Question,Answer\n" "What is \\(x^2\\)?,Square.\n" ",Missing question.\n",
        encoding="utf-8",
    )
    dialog = NotebookLMCsvImportDialog()
    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(csv_path), "CSV files (*.csv)"),
    )

    dialog._choose_csv_file()

    assert dialog.file_path_label.text() == "notebooklm.csv"
    assert dialog.preview_table.rowCount() == 2
    assert dialog.summary_label.text() == "Valid rows: 1 | Invalid rows: 1"
    assert dialog.import_rows() == [("What is $x^2$?", "Square.")]
    assert dialog.import_button.isEnabled()


def test_choose_csv_file_error_and_cancel_paths(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify file picker cancel and parser errors are handled safely."""
    create_managed_folder("Biology")
    csv_path = tmp_path / "notebooklm.csv"
    csv_path.write_text("Question,Answer\nQ?,A.\n", encoding="utf-8")
    dialog = NotebookLMCsvImportDialog()
    warnings: list[str] = []

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: ("", ""),
    )
    dialog._choose_csv_file()
    assert dialog.file_path_label.text() == "No CSV file selected."

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QFileDialog.getOpenFileName",
        lambda *_args, **_kwargs: (str(csv_path), "CSV files (*.csv)"),
    )
    dialog._choose_csv_file()
    assert dialog.import_rows() == [("Q?", "A.")]
    assert dialog.import_button.isEnabled()

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.parse_notebooklm_csv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "boom")
        ),
    )
    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QMessageBox.warning",
        lambda *_args, **_kwargs: warnings.append("warning"),
    )
    dialog._choose_csv_file()

    assert warnings
    assert dialog.preview_table.rowCount() == 0
    assert dialog.summary_label.text() == "Valid rows: 0 | Invalid rows: 0"
    assert dialog.import_rows() == []
    assert not dialog.import_button.isEnabled()


def test_create_target_folder_paths(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify target folder creation handles cancel, validation, and success."""
    dialog = NotebookLMCsvImportDialog()
    warnings: list[str] = []
    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QMessageBox.warning",
        lambda *_args, **_kwargs: warnings.append("warning"),
    )

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Ignored", False),
    )
    dialog._create_target_folder()
    assert dialog.target_folder_combo.count() == 1

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QInputDialog.getText",
        lambda *_args, **_kwargs: ("   ", True),
    )
    dialog._create_target_folder()
    assert warnings

    monkeypatch.setattr(
        "estudai.ui.dialog.notebooklm_import_dialog.QInputDialog.getText",
        lambda *_args, **_kwargs: ("Physics", True),
    )
    dialog._create_target_folder()

    assert dialog.target_folder_combo.count() == 1
    assert dialog.selected_folder_id() is not None
    assert dialog.target_folder_combo.currentText() == "Physics"


def test_reload_folders_shows_hierarchical_labels(app: QApplication) -> None:
    """Verify nested folders are labeled by path in the target combo box."""
    root_folder = create_managed_folder("Biology")
    create_managed_folder("Genetics", parent_id=root_folder.id)

    dialog = NotebookLMCsvImportDialog()

    assert dialog.target_folder_combo.count() == 2
    assert dialog.target_folder_combo.itemText(0) == "Biology"
    assert dialog.target_folder_combo.itemText(1) == "Biology / Genetics"
