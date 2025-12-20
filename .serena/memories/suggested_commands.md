# Suggested Commands for biomapper2

## Package Management (uv)
```bash
# Install all dependencies including dev
uv sync --dev

# Add a new dependency
uv add <package-name>
# NOTE: Commit both pyproject.toml and uv.lock after adding dependencies
```

## Code Quality - Quick Reference
```bash
# Run ALL checks (linting, formatting, type checking, tests)
./scripts/check.sh

# Auto-fix formatting and linting issues
./scripts/fix.sh
```

## Individual Tools
```bash
# Linting
uv run ruff check              # Check for issues
uv run ruff check --fix        # Auto-fix issues

# Formatting
uv run black --check .         # Check formatting
uv run black .                 # Apply formatting

# Type Checking
uv run pyright
```

## Testing
```bash
# Run all tests
uv run pytest

# Verbose output
uv run pytest -v

# Verbose with logging/prints visible
uv run pytest -vs

# Run specific test file
uv run pytest tests/test_specific.py

# Run single test
uv run pytest tests/test_specific.py::test_name

# Skip integration tests
uv run pytest -m "not integration"
```

## Running Examples
```bash
uv run python examples/basic_entity_kg_mapping.py
uv run python examples/basic_dataset_kg_mapping.py
```

## System Utilities (Linux)
```bash
# Standard Linux commands
git, ls, cd, grep, find, cat, head, tail, etc.
```
