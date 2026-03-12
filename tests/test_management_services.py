"""Folder and flashcard management service tests."""

import base64
import os
from pathlib import Path

import pytest

from estudai.services.csv_flashcards import (
    FlashcardRowData,
    add_flashcard_to_folder,
    delete_flashcards_from_folder,
    get_managed_flashcard_media_dir,
    load_flashcards_from_folder,
    replace_flashcards_in_folder,
    sort_flashcard_rows_by_question,
    update_flashcard_in_folder,
)
from estudai.services.folder_storage import (
    create_managed_folder,
    delete_persisted_folder,
    get_registry_path,
    list_persisted_folders,
    move_persisted_folder,
    rename_persisted_folder,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_PNG_1X1_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9W0N4nQAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Use an isolated app data directory for each test."""
    monkeypatch.setenv("ESTUDAI_DATA_DIR", str(tmp_path / "app-data"))


def _write_png(path: Path) -> Path:
    """Write a tiny PNG fixture to disk and return its path."""
    path.write_bytes(_PNG_1X1_BYTES)
    return path


def test_create_rename_delete_managed_folder() -> None:
    """Verify folder creation, rename, and deletion persist correctly."""
    created_folder = create_managed_folder("Biology")
    renamed_folder = rename_persisted_folder(created_folder.id, "Biology 101")
    deleted = delete_persisted_folder(created_folder.id)
    persisted_folders = list_persisted_folders()

    assert created_folder.name == "Biology"
    assert renamed_folder.name == "Biology 101"
    assert deleted is True
    assert persisted_folders == []


def test_flashcard_crud_uses_managed_csv_only() -> None:
    """Verify flashcard add, edit, and delete work through managed CSV storage."""
    created_folder = create_managed_folder("Chemistry")
    folder_path = Path(created_folder.stored_path)
    (folder_path / "cards.csv").write_text(
        "What is NaCl?,Salt.\n",
        encoding="utf-8",
    )

    added_flashcards = add_flashcard_to_folder(folder_path, "What is H2O?", "Water.")
    updated_flashcards = update_flashcard_in_folder(
        folder_path,
        1,
        "What is H2O?",
        "Water molecule.",
    )
    remaining_flashcards = delete_flashcards_from_folder(folder_path, [0])
    loaded_flashcards = load_flashcards_from_folder(folder_path)

    assert len(added_flashcards) == 2
    assert updated_flashcards[1].answer == "Water molecule."
    assert len(remaining_flashcards) == 1
    assert remaining_flashcards[0].question == "What is H2O?"
    assert len(loaded_flashcards) == 1
    assert loaded_flashcards[0].answer == "Water molecule."


def test_add_flashcard_validates_non_empty_fields() -> None:
    """Verify flashcard creation rejects empty question and answer fields."""
    created_folder = create_managed_folder("Physics")
    folder_path = Path(created_folder.stored_path)

    with pytest.raises(ValueError):
        add_flashcard_to_folder(folder_path, "  ", "Valid answer")

    with pytest.raises(ValueError):
        add_flashcard_to_folder(folder_path, "Valid question", "")


def test_flashcard_allows_empty_side_when_same_side_has_image(tmp_path: Path) -> None:
    """Verify each flashcard side may be textless when that side has an image."""
    created_folder = create_managed_folder("Radiology")
    folder_path = Path(created_folder.stored_path)
    question_image = _write_png(tmp_path / "question-only.png")
    answer_image = _write_png(tmp_path / "answer-only.png")

    added_flashcards = add_flashcard_to_folder(
        folder_path,
        "",
        "Visible answer",
        question_image_path=str(question_image),
    )
    updated_flashcards = update_flashcard_in_folder(
        folder_path,
        0,
        "Visible question",
        "",
        answer_image_path=str(answer_image),
    )

    assert added_flashcards[0].question == ""
    assert added_flashcards[0].answer == "Visible answer"
    assert added_flashcards[0].question_image_path is not None
    assert updated_flashcards[0].question == "Visible question"
    assert updated_flashcards[0].answer == ""
    assert updated_flashcards[0].answer_image_path is not None


def test_replace_flashcards_persists_and_validates() -> None:
    """Verify replacing all flashcards validates fields and writes managed CSV."""
    created_folder = create_managed_folder("History")
    folder_path = Path(created_folder.stored_path)

    with pytest.raises(ValueError):
        replace_flashcards_in_folder(folder_path, [(" ", "Valid answer")])

    flashcards = replace_flashcards_in_folder(
        folder_path,
        [
            ("Who discovered Brazil?", "Pedro Alvares Cabral."),
            ("What year was it?", "1500."),
        ],
    )
    loaded_flashcards = load_flashcards_from_folder(folder_path)

    assert len(flashcards) == 2
    assert loaded_flashcards[0].question == "Who discovered Brazil?"
    assert loaded_flashcards[1].answer == "1500."


def test_flashcard_image_crud_copies_and_cleans_managed_media(tmp_path: Path) -> None:
    """Verify image attachments are copied into managed storage and cleaned up."""
    created_folder = create_managed_folder("Anatomy")
    folder_path = Path(created_folder.stored_path)
    question_image = _write_png(tmp_path / "question.png")
    answer_image = _write_png(tmp_path / "answer.png")
    replacement_image = _write_png(tmp_path / "replacement.png")

    added_flashcards = add_flashcard_to_folder(
        folder_path,
        "Identify the structure",
        "It is the hippocampus.",
        question_image_path=str(question_image),
        answer_image_path=str(answer_image),
    )
    added_flashcard = added_flashcards[0]
    question_media_path = folder_path / added_flashcard.question_image_path
    answer_media_path = folder_path / added_flashcard.answer_image_path

    assert added_flashcard.question_image_path is not None
    assert added_flashcard.answer_image_path is not None
    assert question_media_path.exists()
    assert answer_media_path.exists()
    assert question_media_path.parent == get_managed_flashcard_media_dir(folder_path)
    assert answer_media_path.parent == get_managed_flashcard_media_dir(folder_path)

    updated_flashcards = update_flashcard_in_folder(
        folder_path,
        0,
        "Identify the structure",
        "It is the amygdala.",
        question_image_path=str(replacement_image),
        answer_image_path=None,
    )
    updated_flashcard = updated_flashcards[0]
    replacement_media_path = folder_path / updated_flashcard.question_image_path

    assert updated_flashcard.answer == "It is the amygdala."
    assert updated_flashcard.question_image_path is not None
    assert updated_flashcard.answer_image_path is None
    assert replacement_media_path.exists()
    assert question_media_path.exists() is False
    assert answer_media_path.exists() is False

    remaining_flashcards = delete_flashcards_from_folder(folder_path, [0])
    media_dir = get_managed_flashcard_media_dir(folder_path)

    assert remaining_flashcards == []
    assert replacement_media_path.exists() is False
    assert media_dir.exists() is False


def test_replace_flashcards_preserves_existing_relative_image_paths(
    tmp_path: Path,
) -> None:
    """Verify management-style replace keeps already managed relative image paths."""
    created_folder = create_managed_folder("Histology")
    folder_path = Path(created_folder.stored_path)
    source_image = _write_png(tmp_path / "existing.png")
    added_flashcards = add_flashcard_to_folder(
        folder_path,
        "Q1?",
        "A1.",
        question_image_path=str(source_image),
    )
    managed_image_path = added_flashcards[0].question_image_path
    assert managed_image_path is not None

    replaced = replace_flashcards_in_folder(
        folder_path,
        [
            FlashcardRowData(
                question="Q1?",
                answer="A1.",
                question_image_path=managed_image_path,
            )
        ],
    )

    assert replaced[0].question_image_path == managed_image_path
    assert (folder_path / managed_image_path).exists()


def test_sort_flashcard_rows_by_question_uses_normalized_question_text() -> None:
    """Verify alphabetical flashcard sort is deterministic and normalized."""
    sorted_rows = sort_flashcard_rows_by_question(
        [
            (" beta", "b"),
            ("Alpha", "z"),
            ("alpha", "a"),
            ("Gamma", "c"),
        ]
    )

    assert sorted_rows == [
        ("alpha", "a"),
        ("Alpha", "z"),
        (" beta", "b"),
        ("Gamma", "c"),
    ]


def test_move_persisted_folder_reorders_registry_entries() -> None:
    """Verify folder reorder persists in the registry list order."""
    create_managed_folder("Biology")
    create_managed_folder("Chemistry")
    physics = create_managed_folder("Physics")

    reordered = move_persisted_folder(physics.id, 0)

    assert [folder.name for folder in reordered] == [
        "Physics",
        "Biology",
        "Chemistry",
    ]
    assert [folder.name for folder in list_persisted_folders()] == [
        "Physics",
        "Biology",
        "Chemistry",
    ]


def test_list_persisted_folders_handles_corrupt_registry_json() -> None:
    """Verify corrupt registry JSON does not crash folder listing."""
    registry_path = get_registry_path()
    registry_path.write_text("{invalid json", encoding="utf-8")

    assert list_persisted_folders() == []


def test_list_persisted_folders_ignores_non_list_registry_payload() -> None:
    """Verify non-list registry payloads are treated as empty data."""
    registry_path = get_registry_path()
    registry_path.write_text('{"id":"single-object"}', encoding="utf-8")

    assert list_persisted_folders() == []
