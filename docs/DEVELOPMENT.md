# Development Guide

## Setup

Install dependencies using `uv`:

```bash
uv sync
```

## Running the Application

```bash
uv run estudai
```

## Running Tests

Run all tests:

```bash
uv run pytest
```

With coverage:

```bash
uv run pytest --cov=estudai
```

## Code Quality

Format code with Black:

```bash
uv run black src/ tests/
```

Lint with Ruff:

```bash
uv run ruff check src/ tests/
```

Fix Ruff issues automatically:

```bash
uv run ruff check --fix src/ tests/
```

## Windows MSI Packaging and VM Testing

Use the `Windows Package` GitHub Actions workflow to produce an MSI installer.
The generated installer is configured to create an `Estudai` desktop shortcut by default.

### Build artifacts for VM testing (before release)

1. Open the repository on GitHub and go to **Actions**.
2. Select **Windows Package** and click **Run workflow** on the branch you want to test.
3. Open the completed run and download the `windows-installers` artifact.
4. Extract the artifact and copy the `.msi` file to your Windows VM for install testing.

### Create draft prerelease assets from a tag

Push a version tag to trigger the same workflow and attach the MSI to a draft prerelease:

```bash
git tag v1.1.0
git push origin v1.1.0
```

After the run finishes, open **Releases** on GitHub and review the draft prerelease assets before publishing.
