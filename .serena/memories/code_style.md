# Code Style and Conventions

## Formatting
- **Line Length**: 120 characters (configured in pyproject.toml)
- **Formatter**: Black
- **Linter**: Ruff (with isort for imports)
- **Type Checker**: Pyright

## Code Conventions

### Type Hints
- **Required** for all function signatures
- Use `|` union syntax (Python 3.10+): `pd.Series | dict[str, Any]`
- Use `Literal` for string enum parameters: `Literal["all", "missing", "none"]`

### Docstrings
- Google-style docstrings with Args/Returns sections
- Module-level docstrings for files
- Method docstrings for all public methods

Example:
```python
def method(self, param: str, optional: int | None = None) -> dict:
    """
    Brief description.

    Args:
        param: Description of param
        optional: Description of optional param

    Returns:
        Description of return value
    """
```

### Imports
- Sorted by isort (via Ruff)
- Known first-party: `biomapper2`
- Use absolute imports: `from biomapper2.core.annotators.base import BaseAnnotator`

### Naming Conventions
- Classes: PascalCase (`Mapper`, `BaseAnnotator`)
- Functions/Methods: snake_case (`map_entity_to_kg`, `get_annotations`)
- Variables: snake_case (`name_field`, `provided_id_fields`)
- Constants: UPPER_SNAKE_CASE (`KESTREL_API_URL`, `LOG_LEVEL`)

## Architecture Patterns

### Separation of Concerns
| Component | Responsibility | Does NOT do |
|-----------|---------------|-------------|
| **Annotators** | Fetch raw data from APIs, return raw field names | Vocab name mapping, ID cleaning |
| **Normalizer** | Map field names to standard vocabs, clean IDs, validate | API calls |
| **Linker** | Map CURIEs to KG nodes | Normalization |

### Annotator Guidelines
When implementing new annotators:
1. **Use raw API field names** - Return names exactly as API provides
2. **Don't clean IDs** - Normalizer handles prefix stripping, etc.
3. **Grab all available fields** - Include all ID fields the API returns
4. **Reference existing annotators** - Use `kestrel_text.py` as a pattern
