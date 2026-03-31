import subprocess
import sys
from pathlib import Path


def main():
    """Run ruff and black in check mode."""
    project_root = str(Path(__file__).resolve().parents[1])
    print("Checking code with ruff...")
    result = subprocess.run(
        ["ruff", "check", "src/", "tests/"],
        cwd=project_root,
    )
    if result.returncode != 0:
        print("Ruff check failed!")
        sys.exit(1)

    print("Checking code format with black...")
    result = subprocess.run(
        ["black", "--check", "src/", "tests/"],
        cwd=project_root,
    )
    if result.returncode != 0:
        print("Black check failed!")
        sys.exit(1)

    print("✓ Code quality check passed!")


if __name__ == "__main__":
    main()
