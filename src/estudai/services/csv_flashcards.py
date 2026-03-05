"""CSV flashcard loading helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Flashcard:
    """In-memory flashcard loaded from CSV files."""

    question: str
    answer: str
    source_file: Path
    source_line: int


def list_csv_files(folder_path: Path) -> list[Path]:
    """Return CSV files from a folder.

    Args:
        folder_path: Folder containing CSV files.

    Returns:
        list[Path]: Sorted CSV paths in the folder.
    """
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
