"""NotebookLM CSV import dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from estudai.services.folder_storage import (
    create_managed_folder,
    list_persisted_folders,
)
from estudai.services.notebooklm_import import (
    NotebookLMPreviewRow,
    parse_notebooklm_csv,
)


class NotebookLMCsvImportDialog(QDialog):
    """Dialog used to preview and import NotebookLM CSV flashcards."""

    def __init__(self, parent=None) -> None:
        """Initialize dialog state and widgets.

        Args:
            parent: Parent widget.
        """
        super().__init__(parent)
        self._parsed_rows: list[NotebookLMPreviewRow] = []
        self._valid_rows: list[tuple[str, str]] = []
        self._build_ui()
        self._reload_folders()
        self._update_import_button_state()

    def _build_ui(self) -> None:
        """Create and connect dialog widgets."""
        self.setWindowTitle("Import NotebookLM CSV")
        self.resize(850, 500)
        layout = QVBoxLayout(self)

        description = QLabel(
            "Select a NotebookLM CSV file, review rows, and import valid cards."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        file_row = QHBoxLayout()
        self.file_path_label = QLabel("No CSV file selected.")
        self.choose_file_button = QPushButton("Choose CSV File")
        self.choose_file_button.clicked.connect(self._choose_csv_file)
        file_row.addWidget(self.file_path_label)
        file_row.addStretch()
        file_row.addWidget(self.choose_file_button)
        layout.addLayout(file_row)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("Target folder:"))
        self.target_folder_combo = QComboBox()
        self.target_folder_combo.currentIndexChanged.connect(
            self._update_import_button_state
        )
        target_row.addWidget(self.target_folder_combo)
        self.create_folder_button = QPushButton("Create Folder")
        self.create_folder_button.clicked.connect(self._create_target_folder)
        target_row.addWidget(self.create_folder_button)
        layout.addLayout(target_row)

        self.preview_table = QTableWidget(0, 5)
        self.preview_table.setHorizontalHeaderLabels(
            ["Status", "Row", "Question", "Answer", "Reason"]
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents,
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents,
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch
        )
        self.preview_table.horizontalHeader().setSectionResizeMode(
            4,
            QHeaderView.Stretch,
        )
        self.preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.preview_table)

        self.summary_label = QLabel("Valid rows: 0 | Invalid rows: 0")
        layout.addWidget(self.summary_label)

        buttons_row = QHBoxLayout()
        buttons_row.addStretch()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self.accept)
        buttons_row.addWidget(self.cancel_button)
        buttons_row.addWidget(self.import_button)
        layout.addLayout(buttons_row)

    def _reload_folders(self, preferred_folder_id: str | None = None) -> None:
        """Reload target folder options in combo-box.

        Args:
            preferred_folder_id: Folder id selected after reload when available.
        """
        self.target_folder_combo.blockSignals(True)
        self.target_folder_combo.clear()
        for folder in list_persisted_folders():
            self.target_folder_combo.addItem(folder.name, folder.id)
        if self.target_folder_combo.count() == 0:
            self.target_folder_combo.addItem("No folders available", None)
        elif preferred_folder_id is not None:
            preferred_index = self.target_folder_combo.findData(preferred_folder_id)
            if preferred_index >= 0:
                self.target_folder_combo.setCurrentIndex(preferred_index)
        self.target_folder_combo.blockSignals(False)
        self._update_import_button_state()

    def _choose_csv_file(self) -> None:
        """Open file picker, parse CSV, and refresh preview table."""
        selected_file, _ = QFileDialog.getOpenFileName(
            self,
            "Select NotebookLM CSV file",
            "",
            "CSV files (*.csv)",
        )
        if not selected_file:
            return
        self.file_path_label.setText(Path(selected_file).name)
        try:
            parsed = parse_notebooklm_csv(Path(selected_file))
        except OSError as error:
            QMessageBox.warning(self, "Import NotebookLM CSV", str(error))
            return
        self._parsed_rows = parsed.rows
        self._valid_rows = parsed.valid_rows
        self._render_preview_rows()
        self._update_import_button_state()

    def _create_target_folder(self) -> None:
        """Create one managed folder from dialog prompt."""
        folder_name, accepted = QInputDialog.getText(
            self,
            "Create folder",
            "Folder name:",
        )
        if not accepted:
            return
        try:
            created_folder = create_managed_folder(folder_name)
        except ValueError as error:
            QMessageBox.warning(self, "Create folder", str(error))
            return
        self._reload_folders(preferred_folder_id=created_folder.id)

    def _render_preview_rows(self) -> None:
        """Render parsed rows into preview table."""
        self.preview_table.setRowCount(0)
        valid_count = 0
        invalid_count = 0
        for row in self._parsed_rows:
            row_index = self.preview_table.rowCount()
            self.preview_table.insertRow(row_index)
            status = "Valid" if row.is_valid else "Invalid"
            reason = "" if row.is_valid else row.reason
            self.preview_table.setItem(row_index, 0, QTableWidgetItem(status))
            self.preview_table.setItem(
                row_index, 1, QTableWidgetItem(str(row.row_number))
            )
            self.preview_table.setItem(row_index, 2, QTableWidgetItem(row.question))
            self.preview_table.setItem(row_index, 3, QTableWidgetItem(row.answer))
            self.preview_table.setItem(row_index, 4, QTableWidgetItem(reason))
            if row.is_valid:
                valid_count += 1
            else:
                invalid_count += 1
        self.summary_label.setText(
            f"Valid rows: {valid_count} | Invalid rows: {invalid_count}"
        )

    def _update_import_button_state(self) -> None:
        """Update import button enabled state from current selection."""
        has_target_folder = self.selected_folder_id() is not None
        has_valid_rows = bool(self._valid_rows)
        self.import_button.setEnabled(has_target_folder and has_valid_rows)

    def selected_folder_id(self) -> str | None:
        """Return the selected target folder id.

        Returns:
            str | None: Selected folder id or None.
        """
        folder_id = self.target_folder_combo.currentData(Qt.UserRole)
        if isinstance(folder_id, str):
            return folder_id
        return None

    def import_rows(self) -> list[tuple[str, str]]:
        """Return valid parsed rows.

        Returns:
            list[tuple[str, str]]: Valid `(question, answer)` rows.
        """
        return list(self._valid_rows)
