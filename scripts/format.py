import subprocess
import sys
from pathlib import Path


def main():
    """Run ruff and black formatters."""
    project_root = str(Path(__file__).resolve().parents[1])
    print("Running ruff linter and formatter...")
    result = subprocess.run(
        ["ruff", "check", "--fix", "src/", "tests/"],
        cwd=project_root,
    )
    if result.returncode != 0:
        print("Ruff failed!")
        sys.exit(1)

    print("Running black formatter...")
    result = subprocess.run(
        ["black", "src/", "tests/"],
        cwd=project_root,
    )
    if result.returncode != 0:
        print("Black failed!")
        sys.exit(1)

    print("✓ Code formatting complete!")


if __name__ == "__main__":
    main()
