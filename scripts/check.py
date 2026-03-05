import subprocess
import sys


def main():
    """Run ruff and black in check mode."""
    print("Checking code with ruff...")
    result = subprocess.run(
        ["ruff", "check", "src/", "tests/"],
        cwd="/home/daniel-gago/Documents/git/estudai",
    )
    if result.returncode != 0:
        print("Ruff check failed!")
        sys.exit(1)

    print("Checking code format with black...")
    result = subprocess.run(
        ["black", "--check", "src/", "tests/"],
        cwd="/home/daniel-gago/Documents/git/estudai",
    )
    if result.returncode != 0:
        print("Black check failed!")
        sys.exit(1)

    print("✓ Code quality check passed!")


if __name__ == "__main__":
    main()
