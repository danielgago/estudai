"""CSV flashcard loading helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

MANAGED_FLASHCARDS_FILENAME = "_estudai_flashcards.csv"


@dataclass(frozen=True)
class Flashcard:
    """In-memory flashcard loaded from CSV files."""

    question: str
    answer: str
    source_file: Path
    source_line: int


def get_managed_csv_path(folder_path: Path) -> Path:
    """Return the managed CSV path for a folder.

    Args:
        folder_path: Folder containing flashcards.

    Returns:
        Path: Internal managed CSV path.
    """
    return folder_path / MANAGED_FLASHCARDS_FILENAME


def list_csv_files(folder_path: Path) -> list[Path]:
    """Return CSV files from a folder.

    Args:
        folder_path: Folder containing CSV files.

    Returns:
        list[Path]: Sorted CSV paths in the folder.
    """
    managed_csv = get_managed_csv_path(folder_path)
    if managed_csv.exists():
        return [managed_csv]
    return sorted(path for path in folder_path.glob("*.csv") if path.is_file())


def load_flashcards_from_csv(csv_path: Path) -> list[Flashcard]:
    """Load flashcards from one CSV file.

    Args:
        csv_path: CSV path with `question,answer` rows.

    Returns:
        list[Flashcard]: Parsed flashcards.
    """
    flashcards: list[Flashcard] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for line_number, row in enumerate(reader, start=1):
            if len(row) < 2:
                continue
            flashcards.append(
                Flashcard(
                    question=row[0],
                    answer=row[1],
                    source_file=csv_path,
                    source_line=line_number,
                )
            )
    return flashcards


def load_flashcards_from_folder(folder_path: Path) -> list[Flashcard]:
    """Load all flashcards from CSV files in a folder.

    Args:
        folder_path: Folder containing CSV files.

    Returns:
        list[Flashcard]: Combined list of flashcards.
    """
    flashcards: list[Flashcard] = []
    for csv_file in list_csv_files(folder_path):
        flashcards.extend(load_flashcards_from_csv(csv_file))
    return flashcards


def _validate_flashcard_field(value: str, field_name: str) -> str:
    """Validate and normalize one flashcard text field.

    Args:
        value: Field text from user input.
        field_name: Field label used in error messages.

    Returns:
        str: Normalized field value.

    Raises:
        ValueError: If the normalized field is empty.
    """
    normalized_value = value.strip()
    if not normalized_value:
        msg = f"{field_name} cannot be empty."
        raise ValueError(msg)
    return normalized_value


def _write_flashcards_to_csv(
    csv_path: Path,
    flashcard_rows: list[tuple[str, str]],
) -> None:
    """Write flashcard rows into one CSV file.

    Args:
        csv_path: Destination CSV path.
        flashcard_rows: Sequence of `(question, answer)` rows.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(flashcard_rows)


def _flashcards_to_rows(flashcards: list[Flashcard]) -> list[tuple[str, str]]:
    """Convert flashcards into CSV-compatible rows."""
    return [(flashcard.question, flashcard.answer) for flashcard in flashcards]


def _load_or_bootstrap_managed_flashcards(folder_path: Path) -> list[Flashcard]:
    """Load editable flashcards and create managed storage when needed.

    Args:
        folder_path: Folder containing flashcards.

    Returns:
        list[Flashcard]: Editable flashcards from managed CSV.
    """
    managed_csv = get_managed_csv_path(folder_path)
    if managed_csv.exists():
        return load_flashcards_from_csv(managed_csv)

    flashcards = load_flashcards_from_folder(folder_path)
    _write_flashcards_to_csv(
        managed_csv,
        _flashcards_to_rows(flashcards),
    )
    return load_flashcards_from_csv(managed_csv)


def add_flashcard_to_folder(
    folder_path: Path, question: str, answer: str
) -> list[Flashcard]:
    """Add one flashcard to a folder.

    Args:
        folder_path: Target folder path.
        question: Flashcard question text.
        answer: Flashcard answer text.

    Returns:
        list[Flashcard]: Updated flashcards.
    """
    normalized_question = _validate_flashcard_field(question, "Question")
    normalized_answer = _validate_flashcard_field(answer, "Answer")
    flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    flashcard_rows = _flashcards_to_rows(flashcards)
    flashcard_rows.append((normalized_question, normalized_answer))
    managed_csv = get_managed_csv_path(folder_path)
    _write_flashcards_to_csv(managed_csv, flashcard_rows)
    return load_flashcards_from_csv(managed_csv)


def update_flashcard_in_folder(
    folder_path: Path,
    flashcard_index: int,
    question: str,
    answer: str,
) -> list[Flashcard]:
    """Update one flashcard by index inside a folder.

    Args:
        folder_path: Target folder path.
        flashcard_index: Zero-based flashcard index.
        question: Updated question text.
        answer: Updated answer text.

    Returns:
        list[Flashcard]: Updated flashcards.

    Raises:
        IndexError: If index is out of bounds.
    """
    normalized_question = _validate_flashcard_field(question, "Question")
    normalized_answer = _validate_flashcard_field(answer, "Answer")
    flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    if flashcard_index < 0 or flashcard_index >= len(flashcards):
        msg = f"Flashcard index out of range: {flashcard_index}"
        raise IndexError(msg)
    flashcard_rows = _flashcards_to_rows(flashcards)
    flashcard_rows[flashcard_index] = (normalized_question, normalized_answer)
    managed_csv = get_managed_csv_path(folder_path)
    _write_flashcards_to_csv(managed_csv, flashcard_rows)
    return load_flashcards_from_csv(managed_csv)


def delete_flashcards_from_folder(
    folder_path: Path,
    flashcard_indexes: list[int],
) -> list[Flashcard]:
    """Delete selected flashcards by index inside a folder.

    Args:
        folder_path: Target folder path.
        flashcard_indexes: Zero-based indexes to delete.

    Returns:
        list[Flashcard]: Updated flashcards.

    Raises:
        IndexError: If any index is out of bounds.
    """
    flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    if not flashcard_indexes:
        return flashcards

    unique_indexes = sorted(set(flashcard_indexes))
    if unique_indexes[0] < 0 or unique_indexes[-1] >= len(flashcards):
        msg = "Flashcard index out of range."
        raise IndexError(msg)

    index_set = set(unique_indexes)
    flashcard_rows = [
        (card.question, card.answer)
        for index, card in enumerate(flashcards)
        if index not in index_set
    ]
    managed_csv = get_managed_csv_path(folder_path)
    _write_flashcards_to_csv(managed_csv, flashcard_rows)
    return load_flashcards_from_csv(managed_csv)


def replace_flashcards_in_folder(
    folder_path: Path,
    flashcard_rows: list[tuple[str, str]],
) -> list[Flashcard]:
    """Replace all flashcards inside one folder.

    Args:
        folder_path: Target folder path.
        flashcard_rows: Sequence of `(question, answer)` rows.

    Returns:
        list[Flashcard]: Updated flashcards from managed CSV.
    """
    normalized_rows = [
        (
            _validate_flashcard_field(question, "Question"),
            _validate_flashcard_field(answer, "Answer"),
        )
        for question, answer in flashcard_rows
    ]
    managed_csv = get_managed_csv_path(folder_path)
    _write_flashcards_to_csv(managed_csv, normalized_rows)
    return load_flashcards_from_csv(managed_csv)
