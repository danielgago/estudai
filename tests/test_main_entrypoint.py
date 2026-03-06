"""Application entrypoint tests."""

from pathlib import Path

import estudai.main


def test_main_starts_window_and_exits(monkeypatch) -> None:
    """Verify `main` creates app/window and exits with app return code."""
    captured: dict[str, object] = {}

    class _FakeApp:
        def __init__(self, argv) -> None:
            captured["argv"] = argv

        def setWindowIcon(self, icon) -> None:  # noqa: N802
            captured["icon"] = icon

        def exec(self) -> int:
            captured["exec_called"] = True
            return 7

    class _FakeWindow:
        def show(self) -> None:
            captured["window_shown"] = True

    monkeypatch.setattr(estudai.main, "QApplication", _FakeApp)
    monkeypatch.setattr(estudai.main, "QIcon", lambda path: f"ICON:{path}")
    monkeypatch.setattr(estudai.main, "MainWindow", _FakeWindow)
    monkeypatch.setattr(estudai.main, "get_app_icon_path", lambda: "/tmp/estudai.svg")
    monkeypatch.setattr(
        estudai.main.sys, "exit", lambda code: captured.setdefault("exit", code)
    )

    estudai.main.main()

    assert captured["exec_called"] is True
    assert captured["window_shown"] is True
    assert captured["icon"] == "ICON:/tmp/estudai.svg"
    assert captured["exit"] == 7


def test_get_app_icon_path_prefers_frozen_bundle(tmp_path: Path, monkeypatch) -> None:
    """Verify icon lookup prefers bundled ICO path for frozen builds."""
    icon_path = tmp_path / "bundle" / "data" / "estudai.ico"
    icon_path.parent.mkdir(parents=True)
    icon_path.write_bytes(b"\x00\x00\x01\x00")
    (tmp_path / "bundle" / "data" / "estudai.svg").write_text(
        "<svg/>", encoding="utf-8"
    )
    fake_executable = tmp_path / "bundle" / "Estudai.exe"
    fake_executable.write_bytes(b"")

    monkeypatch.setattr(estudai.main.sys, "frozen", True, raising=False)
    monkeypatch.setattr(estudai.main.sys, "executable", str(fake_executable))

    assert estudai.main.get_app_icon_path() == str(icon_path)
