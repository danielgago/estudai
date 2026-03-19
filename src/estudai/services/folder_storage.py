"""Persistent folder storage helpers."""

from __future__ import annotations

import csv
import json
import os
import shutil
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from .csv_flashcards import (
    Flashcard,
    ensure_managed_flashcards,
    get_managed_flashcard_media_dir,
    load_flashcards_from_folder,
    list_source_csv_files,
)
from .study_progress import delete_folder_progress

APP_NAME = "estudai"
ENV_DATA_DIR = "ESTUDAI_DATA_DIR"
REGISTRY_FILENAME = "folders.json"
LIBRARY_FOLDER_NAME = "folder-library"
_UNCHANGED_PARENT = object()


@dataclass(frozen=True)
class PersistedFolder:
    """Represents one persisted folder entry.

    Args:
        id: Stable folder identifier.
        name: Display name shown in the UI.
        source_path: Original imported directory path, or an empty string for
            managed folders created inside Estudai.
        stored_path: Managed directory path used by the application.
        parent_id: Optional parent folder identifier for nested structures.
        sort_order: Zero-based sibling order within the parent folder.
    """

    id: str
    name: str
    source_path: str
    stored_path: str
    parent_id: str | None = None
    sort_order: int = 0


@dataclass(frozen=True)
class ImportedFolderPaths:
    """Represents one imported folder plus all descendant ids.

    Args:
        root_folder: Top-level folder created or updated by the import.
        imported_folder_ids: All imported folder ids in the created subtree.
    """

    root_folder: PersistedFolder
    imported_folder_ids: set[str]


def _validate_folder_name(name: str) -> str:
    """Validate folder name is non-empty after stripping."""
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Folder name cannot be empty.")
    return normalized_name


def get_app_data_dir() -> Path:
    """Return the app data directory using OS-specific defaults."""
    configured_path = os.getenv(ENV_DATA_DIR)
    if configured_path:
        data_dir = Path(configured_path)
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
        data_dir = base / APP_NAME
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        data_dir = base / APP_NAME
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_registry_path() -> Path:
    """Return the persisted folder registry file path."""
    return get_app_data_dir() / REGISTRY_FILENAME


def get_library_dir() -> Path:
    """Return the managed folder library root."""
    library_dir = get_app_data_dir() / LIBRARY_FOLDER_NAME
    library_dir.mkdir(parents=True, exist_ok=True)
    return library_dir


def _deserialize_persisted_folder(
    entry: object,
    *,
    fallback_sort_order: int,
) -> PersistedFolder | None:
    """Build one persisted folder from JSON data when valid.

    Args:
        entry: Raw JSON entry.
        fallback_sort_order: Order used when legacy data has no explicit sibling
            order.

    Returns:
        PersistedFolder | None: Parsed folder metadata when the entry is valid.
    """
    if not isinstance(entry, dict):
        return None

    try:
        folder_id = str(entry["id"])
        folder_name = str(entry["name"])
        source_path = str(entry["source_path"])
        stored_path = str(entry["stored_path"])
    except KeyError, TypeError:
        return None

    parent_id = entry.get("parent_id")
    if parent_id is not None:
        parent_id = str(parent_id)

    sort_order = entry.get("sort_order", fallback_sort_order)
    if not isinstance(sort_order, int):
        sort_order = fallback_sort_order

    return PersistedFolder(
        id=folder_id,
        name=folder_name,
        source_path=source_path,
        stored_path=stored_path,
        parent_id=parent_id,
        sort_order=sort_order,
    )


def _forms_parent_cycle(
    folders_by_id: dict[str, PersistedFolder],
    folder_id: str,
    parent_id: str | None,
) -> bool:
    """Return whether assigning the parent would introduce a cycle.

    Args:
        folders_by_id: Known folders keyed by id.
        folder_id: Folder being validated.
        parent_id: Candidate parent id.

    Returns:
        bool: True when the candidate parent creates a cycle.
    """
    current_parent_id = parent_id
    visited_parent_ids: set[str] = set()
    while current_parent_id is not None:
        if current_parent_id == folder_id or current_parent_id in visited_parent_ids:
            return True
        visited_parent_ids.add(current_parent_id)
        parent_folder = folders_by_id.get(current_parent_id)
        if parent_folder is None:
            return False
        current_parent_id = parent_folder.parent_id
    return False


def _normalize_persisted_folders(
    folders: list[PersistedFolder],
) -> list[PersistedFolder]:
    """Normalize folder hierarchy, sibling order, and traversal order.

    Args:
        folders: Candidate folder metadata.

    Returns:
        list[PersistedFolder]: Folders normalized into pre-order traversal with
        valid parent ids and contiguous sibling ordering.
    """
    if not folders:
        return []

    folder_input_order = {folder.id: index for index, folder in enumerate(folders)}
    folders_by_id = {folder.id: folder for folder in folders}
    sanitized_folders: list[PersistedFolder] = []

    for folder in folders:
        parent_id = folder.parent_id
        if parent_id not in folders_by_id or parent_id == folder.id:
            parent_id = None
        candidate = replace(folder, parent_id=parent_id)
        if _forms_parent_cycle(folders_by_id, candidate.id, candidate.parent_id):
            candidate = replace(candidate, parent_id=None)
        sanitized_folders.append(candidate)

    children_by_parent: dict[str | None, list[PersistedFolder]] = {}
    for folder in sanitized_folders:
        children_by_parent.setdefault(folder.parent_id, []).append(folder)

    for parent_id, siblings in children_by_parent.items():
        children_by_parent[parent_id] = sorted(
            siblings,
            key=lambda folder: (
                folder.sort_order,
                folder_input_order[folder.id],
            ),
        )

    normalized_folders: list[PersistedFolder] = []

    def visit(parent_id: str | None) -> None:
        siblings = children_by_parent.get(parent_id, [])
        for sibling_index, folder in enumerate(siblings):
            normalized_folder = replace(
                folder, parent_id=parent_id, sort_order=sibling_index
            )
            normalized_folders.append(normalized_folder)
            visit(normalized_folder.id)

    visit(None)

    normalized_ids = {folder.id for folder in normalized_folders}
    if len(normalized_ids) == len(sanitized_folders):
        return normalized_folders

    for folder in sanitized_folders:
        if folder.id in normalized_ids:
            continue
        normalized_folders.append(replace(folder, parent_id=None, sort_order=0))
    return _normalize_persisted_folders(normalized_folders)


def _load_registry_entries() -> tuple[list[PersistedFolder], bool]:
    """Read raw persisted folder entries from disk.

    Returns:
        tuple[list[PersistedFolder], bool]: Parsed folders and whether the source
        registry needs to be rewritten.
    """
    registry_path = get_registry_path()
    if not registry_path.exists():
        return [], False

    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], False
    if not isinstance(entries, list):
        return [], False

    persisted_folders: list[PersistedFolder] = []
    needs_save = False
    for entry_index, entry in enumerate(entries):
        persisted_folder = _deserialize_persisted_folder(
            entry,
            fallback_sort_order=entry_index,
        )
        if persisted_folder is None:
            needs_save = True
            continue
        if not Path(persisted_folder.stored_path).exists():
            needs_save = True
            continue
        persisted_folders.append(persisted_folder)

    normalized_folders = _normalize_persisted_folders(persisted_folders)
    if normalized_folders != persisted_folders:
        needs_save = True
    return normalized_folders, needs_save


def list_persisted_folders() -> list[PersistedFolder]:
    """Load persisted folder metadata from disk.

    Returns:
        list[PersistedFolder]: Valid persisted folders in pre-order traversal.
    """
    persisted_folders, needs_save = _load_registry_entries()
    if needs_save:
        save_persisted_folders(persisted_folders)
    return persisted_folders


def save_persisted_folders(folders: list[PersistedFolder]) -> None:
    """Persist folder metadata to disk.

    Args:
        folders: Folder entries to store.
    """
    registry_path = get_registry_path()
    normalized_folders = _normalize_persisted_folders(folders)
    payload = [asdict(folder) for folder in normalized_folders]
    registry_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def _folder_by_id(
    folders: list[PersistedFolder],
    folder_id: str,
) -> PersistedFolder | None:
    """Return one folder by id when present.

    Args:
        folders: Available folder entries.
        folder_id: Folder identifier to look up.

    Returns:
        PersistedFolder | None: Matching folder when found.
    """
    return next((folder for folder in folders if folder.id == folder_id), None)


def _validate_parent_folder(
    folders: list[PersistedFolder],
    parent_id: str | None,
    *,
    moving_folder_id: str | None = None,
) -> None:
    """Validate a candidate parent folder relationship.

    Args:
        folders: Available folder entries.
        parent_id: Candidate parent folder id.
        moving_folder_id: Optional folder being reparented.

    Raises:
        KeyError: If the parent folder does not exist.
        ValueError: If the parent would create a cycle.
    """
    if parent_id is None:
        return

    parent_folder = _folder_by_id(folders, parent_id)
    if parent_folder is None:
        msg = f"Folder not found: {parent_id}"
        raise KeyError(msg)

    if moving_folder_id is None:
        return

    folders_by_id = {folder.id: folder for folder in folders}
    if _forms_parent_cycle(folders_by_id, moving_folder_id, parent_folder.id):
        msg = "A folder cannot be moved into itself or one of its descendants."
        raise ValueError(msg)


def child_folder_ids(folder_id: str) -> set[str]:
    """Return descendant folder ids for one folder.

    Args:
        folder_id: Root folder identifier.

    Returns:
        set[str]: Descendant folder ids, excluding the provided folder id.
    """
    persisted_folders = list_persisted_folders()
    children_by_parent: dict[str | None, list[str]] = {}
    for folder in persisted_folders:
        children_by_parent.setdefault(folder.parent_id, []).append(folder.id)

    descendant_ids: set[str] = set()
    pending_parent_ids = list(children_by_parent.get(folder_id, []))
    while pending_parent_ids:
        child_id = pending_parent_ids.pop()
        if child_id in descendant_ids:
            continue
        descendant_ids.add(child_id)
        pending_parent_ids.extend(children_by_parent.get(child_id, []))
    return descendant_ids


def _reassign_sibling_orders(
    folders: list[PersistedFolder],
    parent_id: str | None,
    *,
    moved_folder: PersistedFolder | None = None,
    insert_index: int | None = None,
) -> list[PersistedFolder]:
    """Reindex siblings for one parent, optionally inserting a moved folder.

    Args:
        folders: Folder entries to update.
        parent_id: Parent whose direct children should be reindexed.
        moved_folder: Optional folder to insert into the sibling list.
        insert_index: Optional insertion index for the moved folder.

    Returns:
        list[PersistedFolder]: Updated folder entries.
    """
    updated_folders = [
        folder
        for folder in folders
        if moved_folder is None or folder.id != moved_folder.id
    ]
    siblings = sorted(
        [folder for folder in updated_folders if folder.parent_id == parent_id],
        key=lambda folder: folder.sort_order,
    )
    if moved_folder is not None:
        sibling_insert_index = len(siblings) if insert_index is None else insert_index
        siblings.insert(
            sibling_insert_index,
            replace(moved_folder, parent_id=parent_id),
        )

    reindexed_by_id = {
        folder.id: replace(folder, parent_id=parent_id, sort_order=sibling_index)
        for sibling_index, folder in enumerate(siblings)
    }
    result: list[PersistedFolder] = []
    seen_folder_ids: set[str] = set()
    source_folders = list(updated_folders)
    if moved_folder is not None:
        source_folders.append(moved_folder)
    for folder in source_folders:
        if folder.id in seen_folder_ids:
            continue
        result.append(reindexed_by_id.get(folder.id, folder))
        seen_folder_ids.add(folder.id)
    return result


def create_managed_folder(
    name: str,
    *,
    parent_id: str | None = None,
) -> PersistedFolder:
    """Create a managed empty folder in app storage.

    Args:
        name: Display name for the new folder.
        parent_id: Optional parent folder id for nested creation.

    Returns:
        PersistedFolder: Created folder metadata.
    """
    normalized_name = _validate_folder_name(name)
    persisted_folders = list_persisted_folders()
    _validate_parent_folder(persisted_folders, parent_id)
    sibling_count = sum(
        1 for folder in persisted_folders if folder.parent_id == parent_id
    )

    folder_id = uuid4().hex
    stored_folder_path = get_library_dir() / folder_id
    stored_folder_path.mkdir(parents=True, exist_ok=False)

    persisted_folder = PersistedFolder(
        id=folder_id,
        name=normalized_name,
        source_path="",
        stored_path=str(stored_folder_path),
        parent_id=parent_id,
        sort_order=sibling_count,
    )
    save_persisted_folders([*persisted_folders, persisted_folder])
    created_folder = _folder_by_id(list_persisted_folders(), folder_id)
    return created_folder if created_folder is not None else persisted_folder


def rename_persisted_folder(folder_id: str, new_name: str) -> PersistedFolder:
    """Rename one persisted folder entry.

    Args:
        folder_id: Persisted folder identifier.
        new_name: New display name.

    Returns:
        PersistedFolder: Updated folder metadata.

    Raises:
        KeyError: If the folder id does not exist.
    """
    normalized_name = _validate_folder_name(new_name)
    persisted_folders = list_persisted_folders()
    updated_folders: list[PersistedFolder] = []
    renamed_folder: PersistedFolder | None = None

    for folder in persisted_folders:
        if folder.id == folder_id:
            renamed_folder = replace(folder, name=normalized_name)
            updated_folders.append(renamed_folder)
            continue
        updated_folders.append(folder)

    if renamed_folder is None:
        msg = f"Folder not found: {folder_id}"
        raise KeyError(msg)

    save_persisted_folders(updated_folders)
    return renamed_folder


def move_persisted_folder(
    folder_id: str,
    new_index: int,
    *,
    parent_id: str | None | object = _UNCHANGED_PARENT,
) -> list[PersistedFolder]:
    """Move one persisted folder entry to a sibling position.

    Args:
        folder_id: Persisted folder identifier.
        new_index: Zero-based target sibling position.
        parent_id: Optional target parent id. When omitted, the folder keeps its
            current parent.

    Returns:
        list[PersistedFolder]: Updated folder ordering.

    Raises:
        KeyError: If the folder or parent id does not exist.
        IndexError: If the target index is out of bounds.
        ValueError: If the move would create a hierarchy cycle.
    """
    persisted_folders = list_persisted_folders()
    moving_folder = _folder_by_id(persisted_folders, folder_id)
    if moving_folder is None:
        msg = f"Folder not found: {folder_id}"
        raise KeyError(msg)

    target_parent_id = (
        moving_folder.parent_id if parent_id is _UNCHANGED_PARENT else parent_id
    )
    _validate_parent_folder(
        persisted_folders,
        target_parent_id,
        moving_folder_id=folder_id,
    )

    sibling_count = sum(
        1
        for folder in persisted_folders
        if folder.parent_id == target_parent_id and folder.id != moving_folder.id
    )
    if new_index < 0 or new_index > sibling_count:
        msg = f"Folder index out of range: {new_index}"
        raise IndexError(msg)

    updated_folders = [folder for folder in persisted_folders if folder.id != folder_id]
    updated_folders = _reassign_sibling_orders(
        updated_folders,
        moving_folder.parent_id,
    )
    updated_folders = _reassign_sibling_orders(
        updated_folders,
        target_parent_id,
        moved_folder=moving_folder,
        insert_index=new_index,
    )
    save_persisted_folders(updated_folders)
    return list_persisted_folders()


def reparent_persisted_folder(
    folder_id: str,
    parent_id: str | None,
    *,
    new_index: int | None = None,
) -> list[PersistedFolder]:
    """Move one folder under a new parent.

    Args:
        folder_id: Folder identifier to move.
        parent_id: New parent folder id, or None to move to the root.
        new_index: Optional zero-based insertion position among the new siblings.

    Returns:
        list[PersistedFolder]: Updated folder ordering.
    """
    persisted_folders = list_persisted_folders()
    sibling_count = sum(
        1 for folder in persisted_folders if folder.parent_id == parent_id
    )
    target_index = sibling_count if new_index is None else new_index
    return move_persisted_folder(folder_id, target_index, parent_id=parent_id)


def delete_persisted_folder(folder_id: str) -> bool:
    """Delete one persisted folder and its descendant folders.

    Args:
        folder_id: Persisted folder identifier.

    Returns:
        bool: True when a folder subtree was removed.
    """
    persisted_folders = list_persisted_folders()
    if _folder_by_id(persisted_folders, folder_id) is None:
        return False

    subtree_ids = {folder_id, *child_folder_ids(folder_id)}
    remaining_folders = [
        folder for folder in persisted_folders if folder.id not in subtree_ids
    ]
    removed_folders = [
        folder for folder in persisted_folders if folder.id in subtree_ids
    ]

    for folder in removed_folders:
        stored_path = Path(folder.stored_path)
        if stored_path.exists():
            shutil.rmtree(stored_path)
        delete_folder_progress(folder.id)

    save_persisted_folders(remaining_folders)
    return True


def _load_previous_flashcards(
    existing_folder: PersistedFolder | None,
) -> tuple[list[Flashcard], TemporaryDirectory[str] | None, Path | None]:
    """Load previous flashcards and preserve managed media during re-import.

    Args:
        existing_folder: Existing folder that is about to be overwritten.

    Returns:
        tuple[list[Flashcard], TemporaryDirectory[str] | None, Path | None]:
            Previous flashcards, temporary media backup directory, and preserved
            media path.
    """
    if existing_folder is None:
        return [], None, None

    previous_flashcards: list[Flashcard] = []
    managed_media_backup_dir: TemporaryDirectory[str] | None = None
    preserved_media_dir: Path | None = None
    previous_stored_path = Path(existing_folder.stored_path)
    if previous_stored_path.exists():
        try:
            previous_flashcards = load_flashcards_from_folder(previous_stored_path)
        except csv.Error, OSError, UnicodeDecodeError, ValueError:
            previous_flashcards = []
        previous_media_dir = get_managed_flashcard_media_dir(previous_stored_path)
        if previous_media_dir.exists():
            managed_media_backup_dir = TemporaryDirectory(dir=get_app_data_dir())
            preserved_media_dir = (
                Path(managed_media_backup_dir.name) / previous_media_dir.name
            )
            shutil.copytree(previous_media_dir, preserved_media_dir)
    return previous_flashcards, managed_media_backup_dir, preserved_media_dir


def _copy_imported_folder_contents(
    source_folder: Path,
    destination_folder: Path,
) -> None:
    """Copy one imported folder into managed storage.

    Args:
        source_folder: Source directory selected by the user.
        destination_folder: Managed directory that should receive the copy.
    """
    if destination_folder.exists():
        shutil.rmtree(destination_folder)
    shutil.copytree(source_folder, destination_folder)


def _copy_imported_csv_contents(
    source_csv: Path,
    destination_folder: Path,
) -> None:
    """Copy one imported CSV file into a managed folder.

    Args:
        source_csv: Source CSV selected from the imported directory tree.
        destination_folder: Managed directory that should receive the CSV file.
    """
    if destination_folder.exists():
        shutil.rmtree(destination_folder)
    destination_folder.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source_csv, destination_folder / source_csv.name)


def _remove_split_source_csv_copies(
    destination_folder: Path,
    source_csv_files: list[Path],
) -> None:
    """Remove root-level CSV copies when they are being split into child folders.

    Args:
        destination_folder: Managed directory that already received the folder copy.
        source_csv_files: Source CSV files that should instead live in child folders.
    """
    for source_csv in source_csv_files:
        copied_csv_path = destination_folder / source_csv.name
        if copied_csv_path.exists():
            copied_csv_path.unlink()


def _sorted_child_directories(folder_path: Path) -> list[Path]:
    """Return child directories sorted for deterministic imports.

    Args:
        folder_path: Directory whose subdirectories should be listed.

    Returns:
        list[Path]: Sorted immediate child directories.
    """
    return sorted(path for path in folder_path.iterdir() if path.is_dir())


def _next_import_sort_order(
    persisted_folders: list[PersistedFolder],
    *,
    existing_folder: PersistedFolder | None,
    parent_id: str | None,
    next_sort_order_by_parent: dict[str | None, int],
) -> int:
    """Return the sort order for one imported folder.

    Args:
        persisted_folders: Current folder registry entries.
        existing_folder: Existing imported folder matched by source path, when any.
        parent_id: Parent folder id for the imported folder.
        next_sort_order_by_parent: Next available sibling positions by parent.

    Returns:
        int: Sort order for the imported folder.
    """
    if existing_folder is not None and existing_folder.parent_id == parent_id:
        return existing_folder.sort_order

    sort_order = next_sort_order_by_parent.setdefault(
        parent_id,
        sum(1 for folder in persisted_folders if folder.parent_id == parent_id),
    )
    next_sort_order_by_parent[parent_id] = sort_order + 1
    return sort_order


def _upsert_imported_folder(
    persisted_folders: list[PersistedFolder],
    *,
    existing_folder: PersistedFolder | None,
    name: str,
    source_path: str,
    stored_path: Path,
    parent_id: str | None,
    next_sort_order_by_parent: dict[str | None, int],
) -> PersistedFolder:
    """Insert or update one imported folder entry in memory.

    Args:
        persisted_folders: Current folder registry entries.
        existing_folder: Existing imported folder matched by source path, when any.
        name: Display name for the imported folder.
        source_path: Original source path backing the imported folder.
        stored_path: Managed directory path used by the application.
        parent_id: Parent folder id for the imported folder.
        next_sort_order_by_parent: Next available sibling positions by parent.

    Returns:
        PersistedFolder: Inserted or updated folder metadata.
    """
    folder_id = existing_folder.id if existing_folder is not None else uuid4().hex
    imported_folder = PersistedFolder(
        id=folder_id,
        name=name,
        source_path=source_path,
        stored_path=str(stored_path),
        parent_id=parent_id,
        sort_order=_next_import_sort_order(
            persisted_folders,
            existing_folder=existing_folder,
            parent_id=parent_id,
            next_sort_order_by_parent=next_sort_order_by_parent,
        ),
    )

    updated_existing = False
    for folder_index, folder in enumerate(persisted_folders):
        if folder.id != folder_id:
            continue
        persisted_folders[folder_index] = imported_folder
        updated_existing = True
        break
    if not updated_existing:
        persisted_folders.append(imported_folder)
    return imported_folder


def _csv_import_folder_name(source_csv: Path) -> str:
    """Return the display name used for one CSV-split imported folder.

    Args:
        source_csv: Source CSV file path.

    Returns:
        str: Folder name shown in the UI.
    """
    return source_csv.stem or source_csv.name


def _import_csv_file(
    source_csv: Path,
    persisted_folders: list[PersistedFolder],
    *,
    parent_id: str | None,
    next_sort_order_by_parent: dict[str | None, int],
) -> ImportedFolderPaths:
    """Import one source CSV file as its own managed folder.

    Args:
        source_csv: Source CSV file to import.
        persisted_folders: Current folder registry that will be updated in place.
        parent_id: Parent folder id for the imported CSV folder.
        next_sort_order_by_parent: Next available sibling positions by parent.

    Returns:
        ImportedFolderPaths: Imported CSV folder plus its managed id set.
    """
    source_key = str(source_csv)
    existing_folder = next(
        (folder for folder in persisted_folders if folder.source_path == source_key),
        None,
    )
    previous_flashcards, managed_media_backup_dir, preserved_media_dir = (
        _load_previous_flashcards(existing_folder)
    )
    stored_folder_path = get_library_dir() / (
        existing_folder.id if existing_folder is not None else uuid4().hex
    )

    try:
        _copy_imported_csv_contents(source_csv, stored_folder_path)
        if preserved_media_dir is not None and preserved_media_dir.exists():
            shutil.copytree(
                preserved_media_dir,
                get_managed_flashcard_media_dir(stored_folder_path),
                dirs_exist_ok=True,
            )
        ensure_managed_flashcards(
            stored_folder_path,
            previous_flashcards=previous_flashcards,
        )
    finally:
        if managed_media_backup_dir is not None:
            managed_media_backup_dir.cleanup()

    imported_folder = _upsert_imported_folder(
        persisted_folders,
        existing_folder=existing_folder,
        name=_csv_import_folder_name(source_csv),
        source_path=source_key,
        stored_path=stored_folder_path,
        parent_id=parent_id,
        next_sort_order_by_parent=next_sort_order_by_parent,
    )
    return ImportedFolderPaths(
        root_folder=imported_folder,
        imported_folder_ids={imported_folder.id},
    )


def _import_folder_tree(
    source_folder: Path,
    persisted_folders: list[PersistedFolder],
    *,
    parent_id: str | None,
    next_sort_order_by_parent: dict[str | None, int],
    split_csv_into_subfolders: bool,
) -> ImportedFolderPaths:
    """Import one source folder and all descendants into managed storage.

    Args:
        source_folder: Source folder to import.
        persisted_folders: Current folder registry that will be updated in place.
        parent_id: Parent folder id for the source root.
        next_sort_order_by_parent: Next available sibling positions by parent.
        split_csv_into_subfolders: Whether directories with multiple CSV files
            should create one child folder per CSV instead of consolidating them.

    Returns:
        ImportedFolderPaths: Imported root folder plus all imported descendant ids.
    """
    source_key = str(source_folder)
    existing_folder = next(
        (folder for folder in persisted_folders if folder.source_path == source_key),
        None,
    )
    previous_flashcards, managed_media_backup_dir, preserved_media_dir = (
        _load_previous_flashcards(existing_folder)
    )
    stored_folder_path = get_library_dir() / (
        existing_folder.id if existing_folder is not None else uuid4().hex
    )
    source_csv_files = list_source_csv_files(source_folder)
    should_split_source_csvs = split_csv_into_subfolders and len(source_csv_files) > 1

    try:
        _copy_imported_folder_contents(source_folder, stored_folder_path)
        if should_split_source_csvs:
            _remove_split_source_csv_copies(stored_folder_path, source_csv_files)
        if preserved_media_dir is not None and preserved_media_dir.exists():
            shutil.copytree(
                preserved_media_dir,
                get_managed_flashcard_media_dir(stored_folder_path),
                dirs_exist_ok=True,
            )
        ensure_managed_flashcards(
            stored_folder_path,
            previous_flashcards=previous_flashcards,
        )
    finally:
        if managed_media_backup_dir is not None:
            managed_media_backup_dir.cleanup()

    imported_folder = _upsert_imported_folder(
        persisted_folders,
        existing_folder=existing_folder,
        name=source_folder.name or source_key,
        source_path=source_key,
        stored_path=stored_folder_path,
        parent_id=parent_id,
        next_sort_order_by_parent=next_sort_order_by_parent,
    )

    imported_folder_ids = {imported_folder.id}
    child_entries: list[tuple[str, str, Path]] = []
    if should_split_source_csvs:
        child_entries.extend(
            (
                _csv_import_folder_name(source_csv).casefold(),
                "csv",
                source_csv,
            )
            for source_csv in source_csv_files
        )
    child_entries.extend(
        (child_directory.name.casefold(), "directory", child_directory)
        for child_directory in _sorted_child_directories(source_folder)
    )

    for _, child_entry_type, child_path in sorted(child_entries):
        if child_entry_type == "csv":
            child_import = _import_csv_file(
                child_path,
                persisted_folders,
                parent_id=imported_folder.id,
                next_sort_order_by_parent=next_sort_order_by_parent,
            )
        else:
            child_import = _import_folder_tree(
                child_path,
                persisted_folders,
                parent_id=imported_folder.id,
                next_sort_order_by_parent=next_sort_order_by_parent,
                split_csv_into_subfolders=split_csv_into_subfolders,
            )
        imported_folder_ids.update(child_import.imported_folder_ids)

    return ImportedFolderPaths(
        root_folder=imported_folder,
        imported_folder_ids=imported_folder_ids,
    )


def import_folder(
    source_folder: Path,
    *,
    parent_id: str | None = None,
    split_csv_into_subfolders: bool = False,
) -> PersistedFolder:
    """Copy a selected folder into managed storage and persist metadata.

    Args:
        source_folder: Folder selected by the user.
        parent_id: Optional parent folder id when importing as a subfolder.
        split_csv_into_subfolders: Whether directories with multiple CSV files
            should create one child folder per CSV instead of consolidating them.

    Returns:
        PersistedFolder: Created or updated root folder entry.
    """
    resolved_source = source_folder.expanduser().resolve()
    if not resolved_source.exists():
        msg = f"Folder not found: {resolved_source}"
        raise FileNotFoundError(msg)
    if not resolved_source.is_dir():
        msg = f"Path is not a directory: {resolved_source}"
        raise NotADirectoryError(msg)

    persisted_folders = list_persisted_folders()
    _validate_parent_folder(persisted_folders, parent_id)
    existing_root = next(
        (
            folder
            for folder in persisted_folders
            if folder.source_path == str(resolved_source)
        ),
        None,
    )
    existing_subtree_ids = (
        {existing_root.id, *child_folder_ids(existing_root.id)}
        if existing_root is not None
        else set()
    )
    import_result = _import_folder_tree(
        resolved_source,
        persisted_folders,
        parent_id=parent_id,
        next_sort_order_by_parent={},
        split_csv_into_subfolders=split_csv_into_subfolders,
    )
    stale_folder_ids = existing_subtree_ids - import_result.imported_folder_ids
    if stale_folder_ids:
        for folder in [
            candidate
            for candidate in persisted_folders
            if candidate.id in stale_folder_ids
        ]:
            stored_path = Path(folder.stored_path)
            if stored_path.exists():
                shutil.rmtree(stored_path)
            delete_folder_progress(folder.id)
        persisted_folders[:] = [
            folder for folder in persisted_folders if folder.id not in stale_folder_ids
        ]
    save_persisted_folders(persisted_folders)
    imported_root = _folder_by_id(
        list_persisted_folders(), import_result.root_folder.id
    )
    return imported_root if imported_root is not None else import_result.root_folder
