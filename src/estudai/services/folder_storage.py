"""Persistent folder storage helpers."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

APP_NAME = "estudai"
ENV_DATA_DIR = "ESTUDAI_DATA_DIR"
REGISTRY_FILENAME = "folders.json"
LIBRARY_FOLDER_NAME = "folder-library"


@dataclass(frozen=True)
class PersistedFolder:
    """Represents one persisted folder entry."""

    id: str
    name: str
    source_path: str
    stored_path: str


def _validate_folder_name(name: str) -> str:
    """Validate and normalize a folder display name.

    Args:
        name: Folder name provided by the user.

    Returns:
        str: Stripped folder name.

    Raises:
        ValueError: If the folder name is empty.
    """
    normalized_name = name.strip()
    if not normalized_name:
        msg = "Folder name cannot be empty."
        raise ValueError(msg)
    return normalized_name


def get_app_data_dir() -> Path:
    """Return the app data directory using OS-specific defaults.

    Returns:
        Path: Directory used for persistent app state.
    """
    configured_path = os.getenv(ENV_DATA_DIR)
    if configured_path:
        data_dir = Path(configured_path)
    elif os.name == "nt":
        appdata = os.getenv("APPDATA")
        base_dir = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        data_dir = base_dir / APP_NAME
    else:
        xdg_data_home = os.getenv("XDG_DATA_HOME")
        base_dir = (
            Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
        )
        data_dir = base_dir / APP_NAME

    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_registry_path() -> Path:
    """Return the persisted folder registry file path.

    Returns:
        Path: JSON file containing persisted folder metadata.
    """
    return get_app_data_dir() / REGISTRY_FILENAME


def get_library_dir() -> Path:
    """Return the managed folder library root.

    Returns:
        Path: Directory where copied user folders are stored.
    """
    library_dir = get_app_data_dir() / LIBRARY_FOLDER_NAME
    library_dir.mkdir(parents=True, exist_ok=True)
    return library_dir


def list_persisted_folders() -> list[PersistedFolder]:
    """Load persisted folder metadata from disk.

    Returns:
        list[PersistedFolder]: Valid persisted folders.
    """
    registry_path = get_registry_path()
    if not registry_path.exists():
        return []

    try:
        entries = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(entries, list):
        return []
    persisted_folders: list[PersistedFolder] = []
    for entry in entries:
        try:
            persisted_folder = PersistedFolder(
                id=str(entry["id"]),
                name=str(entry["name"]),
                source_path=str(entry["source_path"]),
                stored_path=str(entry["stored_path"]),
            )
        except (KeyError, TypeError):
            continue
        if Path(persisted_folder.stored_path).exists():
            persisted_folders.append(persisted_folder)

    if len(persisted_folders) != len(entries):
        save_persisted_folders(persisted_folders)

    return persisted_folders


def save_persisted_folders(folders: list[PersistedFolder]) -> None:
    """Persist folder metadata to disk.

    Args:
        folders: Folder entries to store.
    """
    registry_path = get_registry_path()
    payload = [asdict(folder) for folder in folders]
    registry_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def create_managed_folder(name: str) -> PersistedFolder:
    """Create a managed empty folder in app storage.

    Args:
        name: Display name for the new folder.

    Returns:
        PersistedFolder: Created folder metadata.
    """
    normalized_name = _validate_folder_name(name)
    folder_id = uuid4().hex
    stored_folder_path = get_library_dir() / folder_id
    stored_folder_path.mkdir(parents=True, exist_ok=False)

    persisted_folder = PersistedFolder(
        id=folder_id,
        name=normalized_name,
        source_path="",
        stored_path=str(stored_folder_path),
    )
    persisted_folders = list_persisted_folders()
    persisted_folders.append(persisted_folder)
    save_persisted_folders(persisted_folders)
    return persisted_folder


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
            renamed_folder = PersistedFolder(
                id=folder.id,
                name=normalized_name,
                source_path=folder.source_path,
                stored_path=folder.stored_path,
            )
            updated_folders.append(renamed_folder)
            continue
        updated_folders.append(folder)

    if renamed_folder is None:
        msg = f"Folder not found: {folder_id}"
        raise KeyError(msg)

    save_persisted_folders(updated_folders)
    return renamed_folder


def delete_persisted_folder(folder_id: str) -> bool:
    """Delete one persisted folder and its managed directory.

    Args:
        folder_id: Persisted folder identifier.

    Returns:
        bool: True when a folder was removed.
    """
    persisted_folders = list_persisted_folders()
    remaining_folders: list[PersistedFolder] = []
    removed_folder: PersistedFolder | None = None

    for folder in persisted_folders:
        if folder.id == folder_id:
            removed_folder = folder
            continue
        remaining_folders.append(folder)

    if removed_folder is None:
        return False

    stored_path = Path(removed_folder.stored_path)
    if stored_path.exists():
        shutil.rmtree(stored_path)
    save_persisted_folders(remaining_folders)
    return True


def import_folder(source_folder: Path) -> PersistedFolder:
    """Copy a selected folder into managed storage and persist metadata.

    Args:
        source_folder: Folder selected by the user.

    Returns:
        PersistedFolder: Created or updated persisted folder entry.
    """
    resolved_source = source_folder.expanduser().resolve()
    if not resolved_source.exists():
        msg = f"Folder not found: {resolved_source}"
        raise FileNotFoundError(msg)
    if not resolved_source.is_dir():
        msg = f"Path is not a directory: {resolved_source}"
        raise NotADirectoryError(msg)

    source_key = str(resolved_source)
    persisted_folders = list_persisted_folders()
    existing_folder = next(
        (folder for folder in persisted_folders if folder.source_path == source_key),
        None,
    )
    folder_id = existing_folder.id if existing_folder is not None else uuid4().hex
    stored_folder_path = get_library_dir() / folder_id

    if stored_folder_path.exists():
        shutil.rmtree(stored_folder_path)
    shutil.copytree(resolved_source, stored_folder_path)

    persisted_folder = PersistedFolder(
        id=folder_id,
        name=resolved_source.name or source_key,
        source_path=source_key,
        stored_path=str(stored_folder_path),
    )

    updated_folders: list[PersistedFolder] = []
    replaced = False
    for folder in persisted_folders:
        if folder.id == folder_id:
            updated_folders.append(persisted_folder)
            replaced = True
            continue
        updated_folders.append(folder)
    if not replaced:
        updated_folders.append(persisted_folder)
    save_persisted_folders(updated_folders)

    return persisted_folder
