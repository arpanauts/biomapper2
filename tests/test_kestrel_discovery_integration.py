"""Integration tests for kestrel_discovery against live Kestrel API.

These tests require:
- Live Kestrel API at KESTREL_API_URL
- KESTREL_API_KEY environment variable set

Run with: uv run pytest tests/test_kestrel_discovery_integration.py -v
"""

import pytest
from fastapi.testclient import TestClient

from biomapper2.api.kestrel_discovery import ALIASES, derive_all_presets, fetch_categories
from biomapper2.api.main import app


@pytest.mark.integration
class TestKestrelDiscoveryIntegration:
    """Integration tests against live Kestrel API (4 tests)."""

    def test_fetch_categories_returns_many(self):
        """Live Kestrel returns >10 categories from GET /categories."""
        categories = fetch_categories()
        assert len(categories) > 10
        assert all(isinstance(c, str) for c in categories)
        assert any(c.startswith("biolink:") for c in categories)

    def test_small_molecule_presets_non_empty(self):
        """SmallMolecule presets are non-empty with valid prefix strings."""
        presets = derive_all_presets(ALIASES)
        assert "biolink:SmallMolecule" in presets
        sm_prefixes = presets["biolink:SmallMolecule"]
        assert len(sm_prefixes) > 0
        assert all(isinstance(p, str) and p for p in sm_prefixes)

    def test_protein_presets_non_empty(self):
        """Protein presets are non-empty with valid prefix strings."""
        presets = derive_all_presets(ALIASES)
        assert "biolink:Protein" in presets
        prot_prefixes = presets["biolink:Protein"]
        assert len(prot_prefixes) > 0
        assert all(isinstance(p, str) and p for p in prot_prefixes)

    def test_full_api_response_has_all_fields(self):
        """GET /entity-types returns populated response with all three fields."""
        with TestClient(app) as client:
            response = client.get("/api/v1/entity-types")
            assert response.status_code == 200

            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0

            # Find SmallMolecule and check it has all fields populated
            sm = next((et for et in data if et["type"] == "biolink:SmallMolecule"), None)
            assert sm is not None
            assert sm.get("aliases") is not None
            assert sm.get("defaultPrefixes") is not None
            assert len(sm["defaultPrefixes"]) > 0
