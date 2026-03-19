"""NotebookLM CSV import helpers."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

_LATEX_COMMAND_ESCAPE_PATTERN = re.compile(r"\\\\([A-Za-z]+)")


@dataclass(frozen=True)
class NotebookLMPreviewRow:
    """Represents one parsed CSV row in the preview table.

    Args:
        row_number: One-based CSV line number.
        question: Parsed question text.
        answer: Parsed answer text.
        is_valid: Whether this row can be imported.
        reason: Validation reason when the row is invalid.
    """

    row_number: int
    question: str
    answer: str
    is_valid: bool
    reason: str = ""


@dataclass(frozen=True)
class NotebookLMImportPreview:
    """Parsed CSV preview content.

    Args:
        rows: Row-level validation details for preview rendering.
        valid_rows: Valid `(question, answer)` rows ready to import.
    """

    rows: list[NotebookLMPreviewRow]
    valid_rows: list[tuple[str, str]]


def normalize_inline_latex(value: str) -> str:
    """Normalize inline LaTeX markers from NotebookLM CSV values.

    Args:
        value: Raw value from CSV.

    Returns:
        str: Normalized value with trimmed spaces and inline math markers.
    """
    normalized_value = value.strip()
    normalized_value = normalized_value.replace(r"\(", "$").replace(r"\)", "$")
    return _LATEX_COMMAND_ESCAPE_PATTERN.sub(r"\\\1", normalized_value)


def _is_header_row(row: list[str]) -> bool:
    """Return whether a row matches `Question,Answer` header."""
    if len(row) < 2:
        return False
    first_column = row[0].strip().lstrip("\ufeff").lower()
    second_column = row[1].strip().lower()
    return first_column == "question" and second_column == "answer"


def parse_notebooklm_csv(csv_path: Path) -> NotebookLMImportPreview:
    """Parse a NotebookLM CSV file into valid and invalid rows.

    Args:
        csv_path: CSV file path.

    Returns:
        NotebookLMImportPreview: Parsed rows and valid import payload.
    """
    preview_rows: list[NotebookLMPreviewRow] = []
    valid_rows: list[tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for line_number, row in enumerate(reader, start=1):
            if line_number == 1 and _is_header_row(row):
                continue
            if len(row) != 2:
                preview_rows.append(NotebookLMPreviewRow(
                    row_number=line_number, question="", answer="",
                    is_valid=False, reason="Expected exactly 2 columns: Question,Answer.",
                ))
                continue
            question = normalize_inline_latex(row[0])
            answer = normalize_inline_latex(row[1])
            reason = ""
            if not question:
                reason = "Question cannot be empty."
            elif not answer:
                reason = "Answer cannot be empty."
            is_valid = not reason
            preview_rows.append(NotebookLMPreviewRow(
                row_number=line_number, question=question, answer=answer,
                is_valid=is_valid, reason=reason,
            ))
            if is_valid:
                valid_rows.append((question, answer))
    return NotebookLMImportPreview(rows=preview_rows, valid_rows=valid_rows)
