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

