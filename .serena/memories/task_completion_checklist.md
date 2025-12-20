# Task Completion Checklist

## Before Submitting Code Changes

### 1. Run Quality Checks
```bash
./scripts/check.sh
```
This runs: ruff check → black --check → pyright → pytest -v

### 2. Auto-Fix Issues (if needed)
```bash
./scripts/fix.sh
```
Note: Pyright errors require manual fixing

### 3. Verify Tests Pass
```bash
uv run pytest -v
```

## For New Features

### Test Requirements
- **8 or fewer tests** in a single test file
- Include at least one **end-to-end test** using `Mapper.map_entity_to_kg()`
- Mark integration tests with `@pytest.mark.integration`

### Adding Dependencies
```bash
uv add <package-name>
# CRITICAL: Commit BOTH pyproject.toml AND uv.lock
```

## Before Submitting PRs

1. **Merge latest main**:
   ```bash
   git fetch origin main && git merge origin/main
   ```

2. **Check for duplicates** in pyproject.toml dependencies

3. **Run quality checks**: `./scripts/check.sh`

4. **Verify patterns** match existing annotators:
   - Raw field names (no vocab mapping in annotators)
   - No ID cleaning in annotators

5. **Commit both files** when adding dependencies

## Commit Convention
Use [Conventional Commits](https://www.conventionalcommits.org/):
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `test:` - Tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks
