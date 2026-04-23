"""Tests for equivalent IDs enrichment feature (issue #62)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from biomapper2.core.linker import Linker
from biomapper2.models import Entity


class TestEquivalentIds:
    """Tests for Linker.get_equivalent_ids() and pipeline integration."""

    def test_returns_sorted_equivalent_ids(self):
        """Happy path: returns sorted equivalent CURIEs, including the node itself."""
        mock_response = {
            "NCBIGene:84836": {
                "id": "NCBIGene:84836",
                "equivalent_ids": ["UniProtKB:Q96IU4", "HGNC:28235", "NCBIGene:84836", "ENSEMBL:ENSG00000114779"],
            },
            "MONDO:0005059": {
                "id": "MONDO:0005059",
                "equivalent_ids": ["MONDO:0005059", "DOID:1240"],
            },
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["NCBIGene:84836", "MONDO:0005059"])

        # Sorted, both nodes returned, node IDs included in their own equivalents
        assert result["NCBIGene:84836"] == sorted(
            ["UniProtKB:Q96IU4", "HGNC:28235", "NCBIGene:84836", "ENSEMBL:ENSG00000114779"]
        )
        assert result["MONDO:0005059"] == ["DOID:1240", "MONDO:0005059"]
        assert "NCBIGene:84836" in result["NCBIGene:84836"]

    def test_empty_input_and_missing_nodes(self):
        """Edge cases: empty input returns empty dict; missing node/key returns empty list."""
        # Empty input — no API call
        with patch("biomapper2.core.linker.kestrel_request") as mock_req:
            assert Linker.get_equivalent_ids([]) == {}
            mock_req.assert_not_called()

        # Node not found in KG
        with patch("biomapper2.core.linker.kestrel_request", return_value={}):
            assert Linker.get_equivalent_ids(["UNKNOWN:12345"]) == {}

        # Node object missing equivalent_ids key
        with patch("biomapper2.core.linker.kestrel_request", return_value={"X:1": {"id": "X:1"}}):
            assert Linker.get_equivalent_ids(["X:1"]) == {"X:1": []}

    def test_kestrel_api_error_degrades_gracefully(self):
        """Error path: Kestrel failure logs warning and returns empty dict."""
        with patch("biomapper2.core.linker.kestrel_request", side_effect=Exception("API error")):
            result = Linker.get_equivalent_ids(["NCBIGene:84836"])
        assert result == {}

    def test_entity_model_field(self):
        """Entity model stores, serializes, and defaults kg_equivalent_ids correctly."""
        # Default
        assert Entity(name="test").kg_equivalent_ids == []

        # With values — survives to_dict() and to_series()
        entity = Entity(name="test", kg_equivalent_ids=["HGNC:28235", "UniProtKB:Q96IU4"])
        assert entity.to_dict()["kg_equivalent_ids"] == ["HGNC:28235", "UniProtKB:Q96IU4"]
        assert entity.to_series()["kg_equivalent_ids"] == ["HGNC:28235", "UniProtKB:Q96IU4"]

    def test_map_entity_to_kg_with_match(self):
        """Integration: map_entity_to_kg actually calls get_equivalent_ids via Step 5."""
        from biomapper2.mapper import Mapper

        mapper = MagicMock()

        # Mock Steps 1-4 to produce a resolved entity
        annotation_result = pd.Series({"assigned_ids": {}})
        normalization_result = pd.Series(
            {
                "curies": ["UniProtKB:Q96IU4"],
                "curies_provided": ["UniProtKB:Q96IU4"],
                "curies_assigned": {},
                "invalid_ids_provided": {},
                "invalid_ids_assigned": {},
                "unrecognized_vocabs_provided": [],
                "unrecognized_vocabs_assigned": [],
            }
        )
        linking_result = pd.Series(
            {"kg_ids": {"NCBIGene:84836": ["UniProtKB:Q96IU4"]}, "kg_ids_provided": {}, "kg_ids_assigned": {}}
        )
        resolution_result = pd.Series(
            {"chosen_kg_id": "NCBIGene:84836", "chosen_kg_id_provided": None, "chosen_kg_id_assigned": None}
        )

        mapper.annotation_engine.annotate.return_value = annotation_result
        mapper.normalizer.normalize.return_value = normalization_result
        mapper.normalizer.get_standard_prefix.return_value = None
        mapper.biolink_client.standardize_entity_type.return_value = "biolink:Protein"
        mapper.linker.link.return_value = linking_result
        mapper.resolver.resolve.return_value = resolution_result
        mapper.linker.get_equivalent_ids.return_value = {
            "NCBIGene:84836": ["ENSEMBL:ENSG00000114779", "HGNC:28235", "NCBIGene:84836"]
        }

        # Call the REAL map_entity_to_kg method
        result = Mapper.map_entity_to_kg(
            mapper,
            item={"name": "ABHD14B", "uniprot": "Q96IU4"},
            name_field="name",
            provided_id_fields=["uniprot"],
            entity_type="protein",
        )

        # Verify Step 5 was called and result includes equivalent IDs
        mapper.linker.get_equivalent_ids.assert_called_once_with(["NCBIGene:84836"])
        assert result["kg_equivalent_ids"] == ["ENSEMBL:ENSG00000114779", "HGNC:28235", "NCBIGene:84836"]

    def test_map_entity_to_kg_no_match_skips_enrichment(self):
        """Integration: entity with no KG match skips get_equivalent_ids call."""
        from biomapper2.mapper import Mapper

        mapper = MagicMock()

        mapper.annotation_engine.annotate.return_value = pd.Series({"assigned_ids": {}})
        mapper.normalizer.normalize.return_value = pd.Series(
            {
                "curies": [],
                "curies_provided": [],
                "curies_assigned": {},
                "invalid_ids_provided": {},
                "invalid_ids_assigned": {},
                "unrecognized_vocabs_provided": [],
                "unrecognized_vocabs_assigned": [],
            }
        )
        mapper.normalizer.get_standard_prefix.return_value = None
        mapper.biolink_client.standardize_entity_type.return_value = "biolink:Protein"
        mapper.linker.link.return_value = pd.Series({"kg_ids": {}, "kg_ids_provided": {}, "kg_ids_assigned": {}})
        mapper.resolver.resolve.return_value = pd.Series(
            {"chosen_kg_id": None, "chosen_kg_id_provided": None, "chosen_kg_id_assigned": None}
        )

        result = Mapper.map_entity_to_kg(
            mapper,
            item={"name": "unknown_thing"},
            name_field="name",
            provided_id_fields=[],
            entity_type="protein",
        )

        mapper.linker.get_equivalent_ids.assert_not_called()
        assert result["kg_equivalent_ids"] == []

    def test_dataset_mixed_match_distributes_correctly(self):
        """Dataset pipeline: matched rows get equivalent IDs, unmatched get empty lists."""
        equiv_map = {"NCBIGene:84836": ["HGNC:28235", "NCBIGene:84836"]}
        df = pd.DataFrame({"name": ["ABHD14B", "unknown"], "chosen_kg_id": ["NCBIGene:84836", None]})

        df["kg_equivalent_ids"] = df["chosen_kg_id"].map(lambda kid: [] if pd.isna(kid) else equiv_map.get(kid, []))

        assert df.iloc[0]["kg_equivalent_ids"] == ["HGNC:28235", "NCBIGene:84836"]
        assert df.iloc[1]["kg_equivalent_ids"] == []

    def test_api_response_includes_equivalent_ids(self):
        """API route: extract_mapping_result includes kg_equivalent_ids."""
        from biomapper2.api.routes.mapping import extract_mapping_result

        mapped = {
            "name": "ABHD14B",
            "curies": ["UniProtKB:Q96IU4"],
            "chosen_kg_id": "NCBIGene:84836",
            "kg_equivalent_ids": ["HGNC:28235", "NCBIGene:84836"],
            "kg_ids": {"NCBIGene:84836": ["UniProtKB:Q96IU4"]},
            "assigned_ids": {},
        }
        result = extract_mapping_result(mapped, "ABHD14B")
        assert result.kg_equivalent_ids == ["HGNC:28235", "NCBIGene:84836"]

        # Missing field defaults to empty list
        result_empty = extract_mapping_result({"name": "x", "chosen_kg_id": None}, "x")
        assert result_empty.kg_equivalent_ids == []
