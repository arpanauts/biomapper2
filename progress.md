# Metabolomics Workbench API Annotator - TDD Implementation Plan

**GitHub Issue**: #20 - Add Metabolomics Workbench API Annotator
**Branch**: `metabolomics-workbench-api-annotator`

---

## Overview

Implement a new annotator that queries the Metabolomics Workbench RefMet API to retrieve vocabulary IDs (PubChem, InChIKey, SMILES, RefMet) for metabolite entities.

**API Endpoint**: `GET https://www.metabolomicsworkbench.org/rest/refmet/name/{metabolite_name}/all/`

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `tests/test_metabolomics_workbench.py` | CREATE - Unit tests with mocking |
| `tests/test_metabolomics_workbench_integration.py` | CREATE - Integration tests (real API) |
| `src/biomapper2/core/annotators/metabolomics_workbench.py` | CREATE - Annotator implementation |
| `src/biomapper2/core/annotation_engine.py` | MODIFY - Register annotator |
| `pyproject.toml` | MODIFY - Add pytest markers |

---

## Progress Tracker

### Phase 1: Setup & Basic Structure
- [x] **1.1** Create `tests/test_metabolomics_workbench.py` with first failing test
- [x] **1.2** Create `src/biomapper2/core/annotators/metabolomics_workbench.py` skeleton
- [x] **1.3** Test: `test_annotator_slug` - verify slug = "metabolomics-workbench"
- [x] **1.4** Test: `test_annotator_inheritance` - verify inherits BaseAnnotator

### Phase 2: Single Entity Annotation
- [x] **2.1** Test: `test_get_annotations_returns_correct_structure` (mocked)
- [x] **2.2** Test: `test_vocabulary_mappings` - pubchem.compound, inchikey, smiles, rm
- [x] **2.3** Implement `get_annotations()` method
- [x] **2.4** Implement `_fetch_refmet_data()` helper method

### Phase 3: Edge Cases
- [x] **3.1** Test: `test_empty_response` - metabolite not found returns `[]`
- [x] **3.2** Test: `test_missing_name_field` - entity lacks name field
- [x] **3.3** Test: `test_none_name_value` - name is None
- [x] **3.4** Test: `test_empty_name_value` - name is ""
- [x] **3.5** Test: `test_special_characters_in_name` - URL encoding
- [x] **3.6** Test: `test_api_http_error` - raise exception on HTTP error
- [x] **3.7** Test: `test_api_timeout` - raise exception on timeout
- [x] **3.8** Test: `test_partial_api_response` - handle missing fields gracefully

### Phase 4: Bulk Operations
- [x] **4.1** Test: `test_bulk_returns_series_with_matching_index`
- [x] **4.2** Test: `test_bulk_caches_api_calls` - deduplication
- [x] **4.3** Test: `test_get_annotations_uses_cache_when_provided`
- [x] **4.4** Implement `get_annotations_bulk()` method

### Phase 5: Integration Tests (Real API)
- [x] **5.1** Create `tests/test_metabolomics_workbench_integration.py`
- [x] **5.2** Add pytest markers to `pyproject.toml`
- [x] **5.3** Test: `test_real_api_carnitine` - known metabolite
- [x] **5.4** Test: `test_real_api_nonexistent` - unknown metabolite
- [x] **5.5** Test: `test_real_api_special_characters` - "5-hydroxyindoleacetic acid"

### Phase 6: Annotation Engine Integration
- [x] **6.1** Test: `test_engine_selects_metabolomics_workbench_for_metabolite`
- [x] **6.2** Test: `test_engine_selects_metabolomics_workbench_for_lipid`
- [x] **6.3** Modify `annotation_engine.py` - add import
- [x] **6.4** Modify `annotation_engine.py` - initialize in `__init__`
- [x] **6.5** Modify `annotation_engine.py` - update `_select_annotators()`

### Phase 7: End-to-End Validation
- [x] **7.1** Test: `test_mapper_with_metabolomics_workbench` - full pipeline
- [x] **7.2** Run `./scripts/check.sh` - all quality checks pass
- [x] **7.3** Manual test with example metabolites

---

## Implementation Details

### Vocabulary Mappings

| API Field | Normalizer Vocab | Notes |
|-----------|------------------|-------|
| `pubchem_cid` | `pubchem.compound` | Numeric ID |
| `inchi_key` | `inchikey` | Standard InChIKey format |
| `smiles` | `smiles` | Will be canonicalized by normalizer |
| `refmet_id` | `rm` | Remove "RM" prefix (e.g., "RM0008606" � "0008606") |

### AssignedIDsDict Structure

```python
{
    "metabolomics-workbench": {
        "pubchem.compound": {"10917": {}},
        "inchikey": {"PHIQHXFUZVPYII-ZCFIWIBFSA-N": {}},
        "smiles": {"C[N+](C)(C)C[C@@H](CC(=O)[O-])O": {}},
        "rm": {"0008606": {}}
    }
}
```

### Annotator Class Outline

```python
# src/biomapper2/core/annotators/metabolomics_workbench.py

class MetabolomicsWorkbenchAnnotator(BaseAnnotator):
    slug = "metabolomics-workbench"
    BASE_URL = "https://www.metabolomicsworkbench.org/rest/refmet/name"

    FIELD_TO_VOCAB = {
        "pubchem_cid": "pubchem.compound",
        "inchi_key": "inchikey",
        "smiles": "smiles",
        "refmet_id": "rm",
    }

    def get_annotations(self, entity, name_field, cache=None) -> AssignedIDsDict
    def get_annotations_bulk(self, entities, name_field) -> pd.Series
    def _fetch_refmet_data(self, metabolite_name) -> dict | None
    @staticmethod
    def _clean_refmet_id(refmet_id) -> str  # Remove "RM" prefix
```

### annotation_engine.py Changes

```python
# Line 16 - Add import
from .annotators.metabolomics_workbench import MetabolomicsWorkbenchAnnotator

# Line 24 (in __init__) - Add initialization
self.metabolomics_workbench_annotator = MetabolomicsWorkbenchAnnotator()

# Lines 83-84 - Replace TODO
if entity_type_cleaned in {"metabolite", "smallmolecule", "lipid"}:
    annotators.append(self.metabolomics_workbench_annotator)
```

### Mocking Pattern for Unit Tests

```python
from unittest.mock import patch, MagicMock

@patch('biomapper2.core.annotators.metabolomics_workbench.requests.get')
def test_example(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "name": "Carnitine",
        "pubchem_cid": "10917",
        "inchi_key": "PHIQHXFUZVPYII-ZCFIWIBFSA-N",
        "smiles": "C[N+](C)(C)C[C@@H](CC(=O)[O-])O",
        "refmet_id": "RM0008606"
    }
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_get.return_value = mock_response

    # Test code...
```

### pytest.ini_options Addition

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
]
```

### Running Tests

```bash
# Unit tests only (fast, mocked)
uv run pytest tests/test_metabolomics_workbench.py -v

# Integration tests only (slow, real API)
uv run pytest -m integration -v

# All tests except integration
uv run pytest -m "not integration" -v

# All tests
uv run pytest -v
```

---

## Error Handling Strategy

- **API HTTP errors**: Raise `requests.exceptions.HTTPError`
- **Timeouts**: Raise `requests.exceptions.Timeout`
- **Empty response** (`[]`): Return empty dict `{}`
- **Missing fields in response**: Include only available fields
- **Invalid/empty name**: Return empty dict without API call

---

## Reference Files

- Template: `src/biomapper2/core/annotators/kestrel_text.py`
- Interface: `src/biomapper2/core/annotators/base.py`
- Integration point: `src/biomapper2/core/annotation_engine.py:83-84`
- Type definition: `src/biomapper2/utils.py` (AssignedIDsDict)
