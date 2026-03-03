import subprocess
import sys


def main():
    """Run ruff and black formatters."""
    print("Running ruff linter and formatter...")
    result = subprocess.run(
        ["ruff", "check", "--fix", "src/", "tests/"],
        cwd="/home/daniel-gago/Documents/git/estudai",
    )
    if result.returncode != 0:
        print("Ruff failed!")
        sys.exit(1)

    print("Running black formatter...")
    result = subprocess.run(
        ["black", "src/", "tests/"],
        cwd="/home/daniel-gago/Documents/git/estudai",
    )
    if result.returncode != 0:
        print("Black failed!")
        sys.exit(1)

    print("✓ Code formatting complete!")


if __name__ == "__main__":
    main()
