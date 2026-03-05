"""NotebookLM CSV import parser tests."""

from pathlib import Path

from estudai.services.notebooklm_import import parse_notebooklm_csv


def test_parse_notebooklm_csv_previews_valid_and_invalid_rows(tmp_path: Path) -> None:
    """Verify parser returns valid rows and detailed invalid row reasons."""
    csv_path = tmp_path / "notebooklm.csv"
    csv_path.write_text(
        "Question,Answer\n"
        "What is \\(x^2\\)?,Square.\n"
        ",Missing question.\n"
        "Only one column\n"
        "What is \\\\alpha?,Greek symbol.\n",
        encoding="utf-8",
    )

    parsed = parse_notebooklm_csv(csv_path)

    assert parsed.valid_rows == [
        ("What is $x^2$?", "Square."),
        ("What is \\alpha?", "Greek symbol."),
    ]
    assert len(parsed.rows) == 4
    invalid_rows = [row for row in parsed.rows if not row.is_valid]
    assert len(invalid_rows) == 2
    assert invalid_rows[0].reason == "Question cannot be empty."
    assert invalid_rows[1].reason == "Expected exactly 2 columns: Question,Answer."
