"""Tests for equivalent IDs enrichment feature (issue #62)."""

from unittest.mock import MagicMock, patch

import pandas as pd

from biomapper2.core.linker import Linker
from biomapper2.models import Entity


class TestEquivalentIds:
    """Tests for Linker.get_equivalent_ids() and pipeline integration."""

    def test_returns_filtered_grouped_equivalent_ids(self):
        """Happy path: returns IDs grouped by prefix, filtered to default prefixes, sorted."""
        mock_response = {
            "CHEBI:15365": {
                "id": "CHEBI:15365",
                "equivalent_ids": [
                    "HMDB:HMDB0001879",
                    "CHEBI:15365",
                    "KEGG.COMPOUND:C01405",
                    "PUBCHEM.COMPOUND:2244",
                    "RXCUI:1191",
                    "UMLS:C0004057",
                    "DRUGBANK:DB00945",
                ],
            },
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["CHEBI:15365"])

        # Filtered: RXCUI and UMLS excluded by default prefixes
        assert "CHEBI:15365" in result
        grouped = result["CHEBI:15365"]
        assert "HMDB" in grouped
        assert grouped["HMDB"] == ["HMDB0001879"]
        assert grouped["KEGG.COMPOUND"] == ["C01405"]
        assert grouped["PUBCHEM.COMPOUND"] == ["2244"]
        assert grouped["DRUGBANK"] == ["DB00945"]
        assert "RXCUI" not in grouped
        assert "UMLS" not in grouped
        # Keys sorted alphabetically
        assert list(grouped.keys()) == sorted(grouped.keys())

    def test_unfiltered_with_empty_prefix_list(self):
        """Passing prefixes=[] returns all equivalent IDs unfiltered."""
        mock_response = {
            "X:1": {
                "id": "X:1",
                "equivalent_ids": ["RXCUI:1191", "HMDB:H1", "UMLS:C1"],
            },
        }
        with patch("biomapper2.core.linker.kestrel_request", return_value=mock_response):
            result = Linker.get_equivalent_ids(["X:1"], prefixes=[])

        grouped = result["X:1"]
        assert "RXCUI" in grouped
        assert "HMDB" in grouped
        assert "UMLS" in grouped

    def test_empty_input_and_edge_cases(self):
        """Edge cases: empty input, missing node, missing key."""
        with patch("biomapper2.core.linker.kestrel_request") as mock_req:
            assert Linker.get_equivalent_ids([]) == {}
            mock_req.assert_not_called()

        with patch("biomapper2.core.linker.kestrel_request", return_value={}):
            assert Linker.get_equivalent_ids(["UNKNOWN:12345"]) == {}

        with patch("biomapper2.core.linker.kestrel_request", return_value={"X:1": {"id": "X:1"}}):
            assert Linker.get_equivalent_ids(["X:1"]) == {"X:1": {}}

    def test_kestrel_api_error_degrades_gracefully(self):
        """Error path: Kestrel failure logs warning and returns empty dict."""
        with patch("biomapper2.core.linker.kestrel_request", side_effect=Exception("API error")):
            assert Linker.get_equivalent_ids(["CHEBI:15365"]) == {}

    def test_entity_model_field(self):
        """Entity model stores, serializes, and defaults kg_equivalent_ids correctly."""
        assert Entity(name="test").kg_equivalent_ids == {}

        entity = Entity(name="test", kg_equivalent_ids={"HMDB": ["HMDB0001879"], "CHEBI": ["15365"]})
        assert entity.to_dict()["kg_equivalent_ids"] == {"HMDB": ["HMDB0001879"], "CHEBI": ["15365"]}
        assert entity.to_series()["kg_equivalent_ids"] == {"HMDB": ["HMDB0001879"], "CHEBI": ["15365"]}

    def test_map_entity_to_kg_with_match(self):
        """Integration: map_entity_to_kg calls get_equivalent_ids and returns grouped dict."""
        from biomapper2.mapper import Mapper

        mapper = MagicMock()
        mapper.annotation_engine.annotate.return_value = pd.Series({"assigned_ids": {}})
        mapper.normalizer.normalize.return_value = pd.Series(
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
        mapper.normalizer.get_standard_prefix.return_value = None
        mapper.biolink_client.standardize_entity_type.return_value = "biolink:Protein"
        mapper.linker.link.return_value = pd.Series(
            {"kg_ids": {"NCBIGene:84836": ["UniProtKB:Q96IU4"]}, "kg_ids_provided": {}, "kg_ids_assigned": {}}
        )
        mapper.resolver.resolve.return_value = pd.Series(
            {"chosen_kg_id": "NCBIGene:84836", "chosen_kg_id_provided": None, "chosen_kg_id_assigned": None}
        )
        mapper.linker.get_equivalent_ids.return_value = {
            "NCBIGene:84836": {"ENSEMBL": ["ENSG00000114779"], "HGNC": ["28235"]}
        }

        result = Mapper.map_entity_to_kg(
            mapper,
            item={"name": "ABHD14B", "uniprot": "Q96IU4"},
            name_field="name",
            provided_id_fields=["uniprot"],
            entity_type="protein",
        )

        mapper.linker.get_equivalent_ids.assert_called_once_with(["NCBIGene:84836"])
        assert result["kg_equivalent_ids"] == {"ENSEMBL": ["ENSG00000114779"], "HGNC": ["28235"]}

    def test_map_entity_no_match_returns_empty_dict(self):
        """Integration: entity with no KG match gets empty dict, no API call."""
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
            mapper, item={"name": "unknown"}, name_field="name", provided_id_fields=[], entity_type="protein"
        )

        mapper.linker.get_equivalent_ids.assert_not_called()
        assert result["kg_equivalent_ids"] == {}

    def test_api_response_includes_equivalent_ids(self):
        """API route: extract_mapping_result includes grouped kg_equivalent_ids."""
        from biomapper2.api.routes.mapping import extract_mapping_result

        mapped = {
            "name": "aspirin",
            "curies": ["CHEBI:15365"],
            "chosen_kg_id": "CHEBI:15365",
            "kg_equivalent_ids": {"HMDB": ["HMDB0001879"], "DRUGBANK": ["DB00945"]},
            "kg_ids": {"CHEBI:15365": ["CHEBI:15365"]},
            "assigned_ids": {},
        }
        result = extract_mapping_result(mapped, "aspirin")
        assert result.kg_equivalent_ids == {"HMDB": ["HMDB0001879"], "DRUGBANK": ["DB00945"]}

        result_empty = extract_mapping_result({"name": "x", "chosen_kg_id": None}, "x")
        assert result_empty.kg_equivalent_ids == {}
