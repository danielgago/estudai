"""CSV flashcard loading helpers."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

MANAGED_FLASHCARDS_FILENAME = "_estudai_flashcards.csv"


@dataclass(frozen=True)
class Flashcard:
    """In-memory flashcard loaded from CSV files.

    Args:
        question: Flashcard prompt text.
        answer: Flashcard answer text.
        source_file: CSV file currently backing this flashcard.
        source_line: One-based CSV row index in the current backing file.
        stable_id: Persistent identifier used to track study progress.
        origin_relative_path: Original CSV path within the managed folder, when known.
        origin_line: Original one-based source CSV row index, when known.
    """

    question: str
    answer: str
    source_file: Path
    source_line: int
    stable_id: str = ""
    origin_relative_path: str | None = None
    origin_line: int | None = None


@dataclass(frozen=True)
class _ManagedFlashcardRow:
    """CSV row payload persisted inside the managed flashcard file."""

    question: str
    answer: str
    stable_id: str
    origin_relative_path: str | None
    origin_line: int | None


@dataclass(frozen=True)
class _FlashcardRecord:
    """Normalized flashcard record used while reconciling persistent IDs."""

    question: str
    answer: str
    origin_relative_path: str | None
    origin_line: int | None


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
    return list_source_csv_files(folder_path)


def list_source_csv_files(folder_path: Path) -> list[Path]:
    """Return source CSV files, excluding the managed flashcard file.

    Args:
        folder_path: Folder containing flashcards.

    Returns:
        list[Path]: Sorted source CSV paths.
    """
    return sorted(
        path
        for path in folder_path.glob("*.csv")
        if path.is_file() and path.name != MANAGED_FLASHCARDS_FILENAME
    )


def load_flashcards_from_csv(csv_path: Path) -> list[Flashcard]:
    """Load flashcards from one CSV file.

    Args:
        csv_path: CSV path with flashcard rows.

    Returns:
        list[Flashcard]: Parsed flashcards.
    """
    if csv_path.name == MANAGED_FLASHCARDS_FILENAME:
        return _load_flashcards_from_managed_csv(csv_path)
    return _load_flashcards_from_source_csv(csv_path)


def load_flashcards_from_folder(folder_path: Path) -> list[Flashcard]:
    """Load all flashcards from CSV files in a folder.

    Args:
        folder_path: Folder containing CSV files.

    Returns:
        list[Flashcard]: Combined list of flashcards.
    """
    managed_csv = get_managed_csv_path(folder_path)
    if managed_csv.exists():
        managed_flashcards = load_flashcards_from_csv(managed_csv)
        if managed_flashcards and all(
            flashcard.stable_id for flashcard in managed_flashcards
        ):
            return managed_flashcards
        return ensure_managed_flashcards(
            folder_path,
            previous_flashcards=managed_flashcards,
        )
    flashcards: list[Flashcard] = []
    for csv_file in list_source_csv_files(folder_path):
        flashcards.extend(
            _load_flashcards_from_source_csv(csv_file, folder_path=folder_path)
        )
    return flashcards


def _load_flashcards_from_source_folder(folder_path: Path) -> list[Flashcard]:
    """Load flashcards only from source CSV files in a folder.

    Args:
        folder_path: Folder containing source CSV files.

    Returns:
        list[Flashcard]: Combined source flashcards.
    """
    flashcards: list[Flashcard] = []
    for csv_file in list_source_csv_files(folder_path):
        flashcards.extend(
            _load_flashcards_from_source_csv(csv_file, folder_path=folder_path)
        )
    return flashcards


def ensure_managed_flashcards(
    folder_path: Path,
    *,
    previous_flashcards: list[Flashcard] | None = None,
) -> list[Flashcard]:
    """Ensure a folder has managed flashcards with persistent IDs.

    Args:
        folder_path: Folder containing imported or managed flashcards.
        previous_flashcards: Older managed flashcards used to preserve stable IDs.

    Returns:
        list[Flashcard]: Flashcards loaded from the managed CSV file.
    """
    managed_csv = get_managed_csv_path(folder_path)
    existing_managed_flashcards: list[Flashcard] = []
    if managed_csv.exists():
        existing_managed_flashcards = load_flashcards_from_csv(managed_csv)
        if existing_managed_flashcards and all(
            flashcard.stable_id for flashcard in existing_managed_flashcards
        ):
            return existing_managed_flashcards
        if previous_flashcards is None:
            previous_flashcards = existing_managed_flashcards

    source_flashcards = _load_flashcards_from_source_folder(folder_path)
    if not source_flashcards and existing_managed_flashcards:
        source_flashcards = existing_managed_flashcards

    managed_rows = _build_managed_rows(
        source_flashcards,
        previous_flashcards=previous_flashcards or [],
    )
    _write_managed_flashcards(managed_csv, managed_rows)
    return load_flashcards_from_csv(managed_csv)


def _load_flashcards_from_source_csv(
    csv_path: Path,
    *,
    folder_path: Path | None = None,
) -> list[Flashcard]:
    """Load flashcards from one source CSV file.

    Args:
        csv_path: Source CSV file path.
        folder_path: Folder root used to capture relative origin metadata.

    Returns:
        list[Flashcard]: Parsed flashcards.
    """
    flashcards: list[Flashcard] = []
    origin_relative_path = _origin_relative_path(csv_path, folder_path)
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
                    origin_relative_path=origin_relative_path,
                    origin_line=line_number,
                )
            )
    return flashcards


def _load_flashcards_from_managed_csv(csv_path: Path) -> list[Flashcard]:
    """Load flashcards from the managed CSV file.

    Args:
        csv_path: Managed CSV path.

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
                    stable_id=row[2].strip() if len(row) >= 3 else "",
                    origin_relative_path=_parse_optional_text(
                        row[3] if len(row) >= 4 else ""
                    ),
                    origin_line=_parse_optional_int(row[4] if len(row) >= 5 else ""),
                )
            )
    return flashcards


def _origin_relative_path(csv_path: Path, folder_path: Path | None) -> str | None:
    """Return a folder-relative CSV path when a folder root is known."""
    if folder_path is None:
        return None
    return csv_path.relative_to(folder_path).as_posix()


def _parse_optional_text(value: str) -> str | None:
    """Return a stripped optional text value."""
    normalized_value = value.strip()
    return normalized_value or None


def _parse_optional_int(value: str) -> int | None:
    """Parse one optional positive integer value from CSV metadata."""
    normalized_value = value.strip()
    if not normalized_value:
        return None
    try:
        parsed_value = int(normalized_value)
    except ValueError:
        return None
    return parsed_value if parsed_value > 0 else None


def _record_from_flashcard(flashcard: Flashcard) -> _FlashcardRecord:
    """Build a reconciliation record from one loaded flashcard."""
    return _FlashcardRecord(
        question=flashcard.question,
        answer=flashcard.answer,
        origin_relative_path=flashcard.origin_relative_path,
        origin_line=flashcard.origin_line,
    )


def _record_from_row(question: str, answer: str) -> _FlashcardRecord:
    """Build a reconciliation record from one editable row."""
    return _FlashcardRecord(
        question=question,
        answer=answer,
        origin_relative_path=None,
        origin_line=None,
    )


def _build_managed_rows(
    flashcards: list[Flashcard],
    *,
    previous_flashcards: list[Flashcard],
) -> list[_ManagedFlashcardRow]:
    """Build managed CSV rows while preserving stable IDs when possible.

    Args:
        flashcards: New flashcards that should be persisted.
        previous_flashcards: Prior managed flashcards used for ID reconciliation.

    Returns:
        list[_ManagedFlashcardRow]: Managed CSV rows ready to persist.
    """
    return _reconcile_managed_rows(
        [_record_from_flashcard(flashcard) for flashcard in flashcards],
        previous_flashcards=previous_flashcards,
    )


def _reconcile_managed_rows(
    records: list[_FlashcardRecord],
    *,
    previous_flashcards: list[Flashcard],
) -> list[_ManagedFlashcardRow]:
    """Assign stable IDs to new rows using best-effort matching.

    The matching order prefers:
    1. exact content within the same original source file
    2. exact content anywhere in the folder
    3. same original source line within the same source file
    4. same row index as a final in-app editing fallback

    Args:
        records: New flashcard records that need stable IDs.
        previous_flashcards: Older flashcards available for ID reuse.

    Returns:
        list[_ManagedFlashcardRow]: Managed rows with stable IDs attached.
    """
    matched_previous_indexes = _match_previous_flashcards(
        records,
        previous_flashcards=previous_flashcards,
    )
    managed_rows: list[_ManagedFlashcardRow] = []

    for record, matched_previous_index in zip(
        records, matched_previous_indexes, strict=True
    ):
        previous_flashcard = (
            previous_flashcards[matched_previous_index]
            if matched_previous_index is not None
            else None
        )
        stable_id = (
            previous_flashcard.stable_id
            if previous_flashcard is not None and previous_flashcard.stable_id
            else uuid4().hex
        )
        origin_relative_path = record.origin_relative_path
        if origin_relative_path is None and previous_flashcard is not None:
            origin_relative_path = previous_flashcard.origin_relative_path
        origin_line = record.origin_line
        if origin_line is None and previous_flashcard is not None:
            origin_line = previous_flashcard.origin_line
        managed_rows.append(
            _ManagedFlashcardRow(
                question=record.question,
                answer=record.answer,
                stable_id=stable_id,
                origin_relative_path=origin_relative_path,
                origin_line=origin_line,
            )
        )

    return managed_rows


def _match_previous_flashcards(
    records: list[_FlashcardRecord],
    *,
    previous_flashcards: list[Flashcard],
) -> list[int | None]:
    """Match new records to previous flashcards for stable-ID reuse."""
    matched_previous_indexes: list[int | None] = [None] * len(records)
    used_previous_indexes: set[int] = set()
    previous_records = [
        _record_from_flashcard(flashcard) for flashcard in previous_flashcards
    ]

    key_builders = (
        _content_in_source_key,
        _content_key,
        _origin_line_key,
    )
    for key_builder in key_builders:
        _match_flashcard_records(
            records,
            previous_records=previous_records,
            previous_flashcards=previous_flashcards,
            matched_previous_indexes=matched_previous_indexes,
            used_previous_indexes=used_previous_indexes,
            key_builder=key_builder,
        )

    for record_index, _record in enumerate(records):
        if matched_previous_indexes[record_index] is not None:
            continue
        if record_index >= len(previous_flashcards):
            continue
        previous_flashcard = previous_flashcards[record_index]
        if not previous_flashcard.stable_id or record_index in used_previous_indexes:
            continue
        matched_previous_indexes[record_index] = record_index
        used_previous_indexes.add(record_index)

    return matched_previous_indexes


def _match_flashcard_records(
    records: list[_FlashcardRecord],
    *,
    previous_records: list[_FlashcardRecord],
    previous_flashcards: list[Flashcard],
    matched_previous_indexes: list[int | None],
    used_previous_indexes: set[int],
    key_builder,
) -> None:
    """Apply one matching pass against previous flashcards."""
    available_previous_indexes_by_key: dict[object, list[int]] = defaultdict(list)
    for previous_index, previous_record in enumerate(previous_records):
        if previous_index in used_previous_indexes:
            continue
        previous_flashcard = previous_flashcards[previous_index]
        if not previous_flashcard.stable_id:
            continue
        key = key_builder(previous_record)
        if key is None:
            continue
        available_previous_indexes_by_key[key].append(previous_index)

    for record_index, record in enumerate(records):
        if matched_previous_indexes[record_index] is not None:
            continue
        key = key_builder(record)
        if key is None:
            continue
        available_previous_indexes = available_previous_indexes_by_key.get(key)
        if not available_previous_indexes:
            continue
        matched_previous_index = available_previous_indexes.pop(0)
        matched_previous_indexes[record_index] = matched_previous_index
        used_previous_indexes.add(matched_previous_index)


def _content_in_source_key(record: _FlashcardRecord) -> tuple[str, str, str] | None:
    """Return a key for exact content within one original source file."""
    if record.origin_relative_path is None:
        return None
    return (record.origin_relative_path, record.question, record.answer)


def _content_key(record: _FlashcardRecord) -> tuple[str, str]:
    """Return a key for exact flashcard content."""
    return (record.question, record.answer)


def _origin_line_key(record: _FlashcardRecord) -> tuple[str, int] | None:
    """Return a key for one original source line inside one source file."""
    if record.origin_relative_path is None or record.origin_line is None:
        return None
    return (record.origin_relative_path, record.origin_line)


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


def normalize_flashcard_fields(question: str, answer: str) -> tuple[str, str]:
    """Validate and normalize one flashcard question/answer pair.

    Args:
        question: Raw question text.
        answer: Raw answer text.

    Returns:
        tuple[str, str]: Normalized question and answer text.
    """
    return (
        _validate_flashcard_field(question, "Question"),
        _validate_flashcard_field(answer, "Answer"),
    )


def normalize_flashcard_sort_text(value: str) -> str:
    """Normalize text used for deterministic flashcard ordering.

    Args:
        value: Raw text used for sorting.

    Returns:
        str: Case-insensitive normalized text.
    """
    return " ".join(value.strip().split()).casefold()


def flashcard_question_sort_key(
    question: str, answer: str
) -> tuple[str, str, str, str]:
    """Return a deterministic sort key for one flashcard row.

    Args:
        question: Flashcard question text.
        answer: Flashcard answer text.

    Returns:
        tuple[str, str, str, str]: Normalized and raw sort values.
    """
    return (
        normalize_flashcard_sort_text(question),
        normalize_flashcard_sort_text(answer),
        question,
        answer,
    )


def sort_flashcard_rows_by_question(
    flashcard_rows: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return flashcard rows sorted alphabetically by normalized question text.

    Args:
        flashcard_rows: Flashcard question/answer rows.

    Returns:
        list[tuple[str, str]]: Sorted rows.
    """
    return sorted(
        flashcard_rows,
        key=lambda row: flashcard_question_sort_key(row[0], row[1]),
    )


def _write_csv_rows(csv_path: Path, rows: list[tuple[str, ...]]) -> None:
    """Write CSV rows into one file.

    Args:
        csv_path: Destination CSV path.
        rows: Sequence of CSV rows to persist.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)


def _write_managed_flashcards(
    csv_path: Path,
    flashcard_rows: list[_ManagedFlashcardRow],
) -> None:
    """Write managed flashcards with stable metadata into one CSV file.

    Args:
        csv_path: Destination managed CSV path.
        flashcard_rows: Managed flashcard rows.
    """
    _write_csv_rows(
        csv_path,
        [
            (
                row.question,
                row.answer,
                row.stable_id,
                row.origin_relative_path or "",
                str(row.origin_line or ""),
            )
            for row in flashcard_rows
        ],
    )


def _flashcards_to_rows(flashcards: list[Flashcard]) -> list[tuple[str, str]]:
    """Convert flashcards into editable question/answer rows.

    Args:
        flashcards: Flashcards to serialize.

    Returns:
        list[tuple[str, str]]: CSV-compatible question/answer rows.
    """
    return [(flashcard.question, flashcard.answer) for flashcard in flashcards]


def _load_or_bootstrap_managed_flashcards(folder_path: Path) -> list[Flashcard]:
    """Load editable flashcards and create managed storage when needed.

    Args:
        folder_path: Folder containing flashcards.

    Returns:
        list[Flashcard]: Editable flashcards from managed CSV.
    """
    return ensure_managed_flashcards(folder_path)


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
    normalized_question, normalized_answer = normalize_flashcard_fields(
        question,
        answer,
    )
    flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    managed_rows = [
        _ManagedFlashcardRow(
            question=flashcard.question,
            answer=flashcard.answer,
            stable_id=flashcard.stable_id or uuid4().hex,
            origin_relative_path=flashcard.origin_relative_path,
            origin_line=flashcard.origin_line,
        )
        for flashcard in flashcards
    ]
    managed_rows.append(
        _ManagedFlashcardRow(
            question=normalized_question,
            answer=normalized_answer,
            stable_id=uuid4().hex,
            origin_relative_path=None,
            origin_line=None,
        )
    )
    managed_csv = get_managed_csv_path(folder_path)
    _write_managed_flashcards(managed_csv, managed_rows)
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
    normalized_question, normalized_answer = normalize_flashcard_fields(
        question,
        answer,
    )
    flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    if flashcard_index < 0 or flashcard_index >= len(flashcards):
        msg = f"Flashcard index out of range: {flashcard_index}"
        raise IndexError(msg)
    managed_rows = [
        _ManagedFlashcardRow(
            question=flashcard.question,
            answer=flashcard.answer,
            stable_id=flashcard.stable_id or uuid4().hex,
            origin_relative_path=flashcard.origin_relative_path,
            origin_line=flashcard.origin_line,
        )
        for flashcard in flashcards
    ]
    managed_rows[flashcard_index] = _ManagedFlashcardRow(
        question=normalized_question,
        answer=normalized_answer,
        stable_id=managed_rows[flashcard_index].stable_id,
        origin_relative_path=managed_rows[flashcard_index].origin_relative_path,
        origin_line=managed_rows[flashcard_index].origin_line,
    )
    managed_csv = get_managed_csv_path(folder_path)
    _write_managed_flashcards(managed_csv, managed_rows)
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
    managed_rows = [
        _ManagedFlashcardRow(
            question=card.question,
            answer=card.answer,
            stable_id=card.stable_id or uuid4().hex,
            origin_relative_path=card.origin_relative_path,
            origin_line=card.origin_line,
        )
        for index, card in enumerate(flashcards)
        if index not in index_set
    ]
    managed_csv = get_managed_csv_path(folder_path)
    _write_managed_flashcards(managed_csv, managed_rows)
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
        normalize_flashcard_fields(question, answer)
        for question, answer in flashcard_rows
    ]
    existing_flashcards = _load_or_bootstrap_managed_flashcards(folder_path)
    managed_rows = _reconcile_managed_rows(
        [_record_from_row(question, answer) for question, answer in normalized_rows],
        previous_flashcards=existing_flashcards,
    )
    managed_csv = get_managed_csv_path(folder_path)
    _write_managed_flashcards(managed_csv, managed_rows)
    return load_flashcards_from_csv(managed_csv)
