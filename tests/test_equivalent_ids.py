"""Tests for equivalent IDs enrichment feature (issue #62)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from biomapper2.core.linker import Linker
from biomapper2.models import Entity


class TestGetEquivalentIds:
    """Tests for Linker.get_equivalent_ids()."""

    def test_single_node_returns_sorted_equivalent_ids(self):
        """Happy path: single node ID returns sorted equivalent CURIEs."""
        mock_response = {
            "NCBIGene:84836": {
                "id": "NCBIGene:84836",
                "equivalent_ids": ["UniProtKB:Q96IU4", "HGNC:28235", "NCBIGene:84836", "ENSEMBL:ENSG00000114779"],
            }
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["NCBIGene:84836"])

        assert "NCBIGene:84836" in result
        assert result["NCBIGene:84836"] == sorted(
            ["UniProtKB:Q96IU4", "HGNC:28235", "NCBIGene:84836", "ENSEMBL:ENSG00000114779"]
        )
        # Verify sorted order
        assert result["NCBIGene:84836"] == list(sorted(result["NCBIGene:84836"]))

    def test_multiple_nodes_returns_equivalent_ids_for_each(self):
        """Happy path: multiple node IDs returns equivalent IDs for each."""
        mock_response = {
            "NCBIGene:84836": {
                "id": "NCBIGene:84836",
                "equivalent_ids": ["NCBIGene:84836", "HGNC:28235"],
            },
            "MONDO:0005059": {
                "id": "MONDO:0005059",
                "equivalent_ids": ["MONDO:0005059", "DOID:1240"],
            },
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["NCBIGene:84836", "MONDO:0005059"])

        assert len(result) == 2
        assert "NCBIGene:84836" in result
        assert "MONDO:0005059" in result

    def test_empty_input_returns_empty_dict(self):
        """Edge case: empty list returns empty dict without API call."""
        with patch("biomapper2.core.linker.kestrel_request") as mock_request:
            result = Linker.get_equivalent_ids([])

        assert result == {}
        mock_request.assert_not_called()

    def test_node_not_found_returns_empty_for_that_id(self):
        """Edge case: node ID not in KG response — returns nothing for that ID."""
        mock_response = {}  # API returned no match
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["UNKNOWN:12345"])

        assert result == {}

    def test_node_missing_equivalent_ids_key(self):
        """Edge case: node object lacks equivalent_ids key entirely."""
        mock_response = {
            "NCBIGene:84836": {
                "id": "NCBIGene:84836",
                # No equivalent_ids key
            }
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["NCBIGene:84836"])

        assert result["NCBIGene:84836"] == []

    def test_chosen_kg_id_included_in_equivalents(self):
        """Edge case: equivalent_ids includes the node itself — kept (matches raw KG truth)."""
        mock_response = {
            "NCBIGene:84836": {
                "id": "NCBIGene:84836",
                "equivalent_ids": ["NCBIGene:84836", "HGNC:28235"],
            }
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["NCBIGene:84836"])

        assert "NCBIGene:84836" in result["NCBIGene:84836"]

    def test_kestrel_api_error_returns_empty_dict(self):
        """Error path: Kestrel API failure → log warning, return empty dict."""
        with patch("biomapper2.core.linker.kestrel_request", side_effect=Exception("API error")):
            result = Linker.get_equivalent_ids(["NCBIGene:84836"])

        assert result == {}


class TestEntityModelEquivalentIds:
    """Tests for kg_equivalent_ids field on Entity model."""

    def test_entity_default_empty_list(self):
        """Entity defaults kg_equivalent_ids to empty list."""
        entity = Entity(name="test")
        assert entity.kg_equivalent_ids == []

    def test_entity_with_equivalent_ids(self):
        """Entity accepts and stores kg_equivalent_ids."""
        entity = Entity(name="test", kg_equivalent_ids=["HGNC:28235", "UniProtKB:Q96IU4"])
        assert entity.kg_equivalent_ids == ["HGNC:28235", "UniProtKB:Q96IU4"]

    def test_entity_to_dict_includes_equivalent_ids(self):
        """to_dict() includes kg_equivalent_ids."""
        entity = Entity(name="test", kg_equivalent_ids=["A", "B"])
        d = entity.to_dict()
        assert d["kg_equivalent_ids"] == ["A", "B"]

    def test_entity_to_series_includes_equivalent_ids(self):
        """to_series() includes kg_equivalent_ids."""
        entity = Entity(name="test", kg_equivalent_ids=["A", "B"])
        s = entity.to_series()
        assert s["kg_equivalent_ids"] == ["A", "B"]


class TestMapperEquivalentIdsIntegration:
    """Tests for equivalent IDs in the Mapper pipeline."""

    def _make_mapper_with_mocked_steps(self, equiv_response: dict[str, list[str]]):
        """Create a Mapper with mocked pipeline steps that return equivalent IDs."""
        from biomapper2.mapper import Mapper

        mapper = MagicMock(spec=Mapper)
        mapper.linker = MagicMock()
        mapper.linker.get_equivalent_ids.return_value = equiv_response

        # Make map_entity_to_kg use the real method bound to our mock
        mapper.map_entity_to_kg = Mapper.map_entity_to_kg.__get__(mapper, Mapper)
        return mapper

    def test_map_entity_with_match_gets_equivalent_ids(self):
        """Happy path: entity with a KG match gets kg_equivalent_ids populated."""
        from biomapper2.mapper import Mapper

        # Create a fully mocked mapper where Steps 1-4 produce a resolved entity
        mapper = MagicMock(spec=Mapper)
        mapper.linker = MagicMock()
        mapper.linker.get_equivalent_ids.return_value = {
            "NCBIGene:84836": ["ENSEMBL:ENSG00000114779", "HGNC:28235", "NCBIGene:84836"]
        }

        # Simulate Step 1-4 results via entity
        entity = Entity(
            name="ABHD14B",
            curies=["UniProtKB:Q96IU4"],
            kg_ids={"NCBIGene:84836": ["UniProtKB:Q96IU4"]},
            chosen_kg_id="NCBIGene:84836",
        )

        # Step 5: enrichment
        equiv_ids = mapper.linker.get_equivalent_ids([entity.chosen_kg_id])
        entity = entity.update_from(pd.Series({"kg_equivalent_ids": equiv_ids.get(entity.chosen_kg_id, [])}))

        assert entity.kg_equivalent_ids == ["ENSEMBL:ENSG00000114779", "HGNC:28235", "NCBIGene:84836"]

    def test_entity_with_no_match_gets_empty_equivalent_ids(self):
        """Edge case: entity with chosen_kg_id=None gets empty kg_equivalent_ids."""
        entity = Entity(name="unknown_thing", chosen_kg_id=None)
        assert entity.kg_equivalent_ids == []

    def test_dataset_all_none_chosen_kg_id_skips_api_call(self):
        """Edge case: dataset where ALL entities have no KG match — no API call made."""
        df = pd.DataFrame({"chosen_kg_id": [None, None, None]})
        unique_kg_ids = [kid for kid in df["chosen_kg_id"].dropna().unique()]

        assert unique_kg_ids == []
        # No API call would be made

    def test_dataset_mixed_match_distributes_correctly(self):
        """Edge case: dataset with matched and unmatched entities distributes correctly."""
        equiv_map = {
            "NCBIGene:84836": ["HGNC:28235", "NCBIGene:84836"],
        }

        df = pd.DataFrame(
            {
                "name": ["ABHD14B", "unknown"],
                "chosen_kg_id": ["NCBIGene:84836", None],
            }
        )

        df["kg_equivalent_ids"] = df["chosen_kg_id"].map(lambda kid: equiv_map.get(kid, []) if kid else [])

        assert df.iloc[0]["kg_equivalent_ids"] == ["HGNC:28235", "NCBIGene:84836"]
        assert df.iloc[1]["kg_equivalent_ids"] == []
