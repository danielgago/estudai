"""Non-GUI smoke tests."""


def test_package_importable() -> None:
    """Verify the package imports in minimal environments."""
    import estudai

    assert estudai is not None
