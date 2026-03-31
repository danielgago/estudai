"""Error-path tests for service robustness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from estudai.services.study_progress import (
    FlashcardProgressEntry,
    load_study_progress,
    save_progress_entries,
    reviewed_progress,
)
from estudai.services.csv_flashcards import (
    load_flashcards_from_csv,
    load_flashcards_from_folder,
)
from estudai.services.settings import (
    validate_notification_sound_file,
    copy_notification_sound_file,
)


@pytest.fixture(autouse=True)
def _isolated(isolated_data_dir: Path) -> None:
    """Ensure each test uses an isolated data directory."""


@pytest.mark.unit
class TestStudyProgressErrorPaths:
    """Verify study-progress loading handles corrupt and missing data."""

    def test_load_returns_empty_when_file_is_missing(self) -> None:
        """Loading progress when no file exists returns an empty dict."""
        assert load_study_progress() == {}

    def test_load_returns_empty_when_json_is_corrupt(
        self, isolated_data_dir: Path
    ) -> None:
        """Loading progress from a truncated JSON file returns empty."""
        from estudai.services.study_progress import get_study_progress_path

        progress_path = get_study_progress_path()
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text("{invalid json content", encoding="utf-8")
        assert load_study_progress() == {}

    def test_load_returns_empty_when_json_is_not_a_dict(
        self, isolated_data_dir: Path
    ) -> None:
        """Loading progress from a non-dict top-level JSON returns empty."""
        from estudai.services.study_progress import get_study_progress_path

        progress_path = get_study_progress_path()
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        progress_path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert load_study_progress() == {}

    def test_save_and_load_roundtrip(self, isolated_data_dir: Path) -> None:
        """Progress entries survive a save/load roundtrip."""
        entries = [
            FlashcardProgressEntry(
                folder_id="f1",
                flashcard_id="card-1",
                progress=reviewed_progress(correct_count=2, wrong_count=1),
            ),
        ]
        save_progress_entries(entries)
        loaded = load_study_progress()
        assert "f1" in loaded
        assert "card-1" in loaded["f1"]
        assert loaded["f1"]["card-1"].correct_count == 2
        assert loaded["f1"]["card-1"].wrong_count == 1

    def test_save_skips_empty_entries(self) -> None:
        """Saving an empty list of entries is a no-op."""
        save_progress_entries([])


@pytest.mark.unit
class TestFlashcardLoadingErrorPaths:
    """Verify CSV flashcard loading handles invalid data gracefully."""

    def test_load_from_missing_csv_raises(self, tmp_path: Path) -> None:
        """Loading flashcards from a non-existent CSV raises an error."""
        missing_csv = tmp_path / "does-not-exist.csv"
        with pytest.raises(FileNotFoundError):
            load_flashcards_from_csv(missing_csv)

    def test_load_from_empty_folder_returns_empty(self, tmp_path: Path) -> None:
        """Loading flashcards from an empty folder returns an empty list."""
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()
        assert load_flashcards_from_folder(empty_folder) == []

    def test_load_from_csv_with_no_data_rows_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """A CSV with a single incomplete row produces no flashcards."""
        csv_path = tmp_path / "single-col.csv"
        csv_path.write_text("only_one_column\n", encoding="utf-8")
        assert load_flashcards_from_csv(csv_path) == []


@pytest.mark.unit
class TestSoundFileValidationErrorPaths:
    """Verify notification sound file validation rejects bad input."""

    def test_missing_sound_file_raises(self, tmp_path: Path) -> None:
        """Validation fails for a non-existent sound file."""
        missing = tmp_path / "missing.mp3"
        with pytest.raises(FileNotFoundError):
            validate_notification_sound_file(missing)

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        """Validation fails for an unsupported file extension."""
        bad_file = tmp_path / "song.ogg"
        bad_file.write_bytes(b"fake")
        with pytest.raises(ValueError, match="Unsupported"):
            validate_notification_sound_file(bad_file)

    def test_copy_sound_file_with_empty_slot_name_raises(
        self, tmp_path: Path, isolated_data_dir: Path
    ) -> None:
        """Copying a sound file with an empty slot name raises ValueError."""
        sound_file = tmp_path / "alert.mp3"
        sound_file.write_bytes(b"fake-mp3")
        with pytest.raises(ValueError, match="slot name"):
            copy_notification_sound_file(sound_file, slot_name="   ")
