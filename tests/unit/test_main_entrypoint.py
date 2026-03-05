"""Application entrypoint tests."""

import estudai.main


def test_main_starts_window_and_exits(monkeypatch) -> None:
    """Verify `main` creates app/window and exits with app return code."""
    captured: dict[str, object] = {}

    class _FakeApp:
        def __init__(self, argv) -> None:
            captured["argv"] = argv

        def exec(self) -> int:
            captured["exec_called"] = True
            return 7

    class _FakeWindow:
        def show(self) -> None:
            captured["window_shown"] = True

    monkeypatch.setattr(estudai.main, "QApplication", _FakeApp)
    monkeypatch.setattr(estudai.main, "MainWindow", _FakeWindow)
    monkeypatch.setattr(
        estudai.main.sys, "exit", lambda code: captured.setdefault("exit", code)
    )

    estudai.main.main()

    assert captured["exec_called"] is True
    assert captured["window_shown"] is True
    assert captured["exit"] == 7
