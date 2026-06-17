"""Unit tests for the curated gene-symbol fallback resolver.

The resolver is a no-op for non-curated symbols, and for the curated six it accepts the canonical
human NCBIGene CURIE only after /get-nodes confirms the node carries the queried symbol as a synonym
AND an HGNC equivalent. All Kestrel access is mocked so these run offline.
"""

from unittest.mock import patch

from biomapper2.core.gene_symbol_resolver import GeneSymbolResolver


def _node(synonyms, equivalent_ids):
    return {"synonyms": synonyms, "equivalent_ids": equivalent_ids}


class TestGeneSymbolResolver:
    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_resolves_curated_with_symbol_synonym_and_hgnc(self, mock_req):
        mock_req.return_value = {"NCBIGene:2688": _node(["SOMATROPIN", "GH1", "GHN"], ["NCBIGene:2688", "HGNC:4261"])}
        assert GeneSymbolResolver().resolve("GH1") == "NCBIGene:2688"

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_case_insensitive_symbol(self, mock_req):
        mock_req.return_value = {"NCBIGene:1493": _node(["BELATACEPT", "CTLA4"], ["HGNC:2505"])}
        assert GeneSymbolResolver().resolve("ctla4") == "NCBIGene:1493"

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_non_curated_symbol_is_noop(self, mock_req):
        """A symbol outside the curated six returns None without ever calling Kestrel."""
        assert GeneSymbolResolver().resolve("TP53") is None
        mock_req.assert_not_called()

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_rejects_when_node_lacks_queried_symbol(self, mock_req):
        """Curated symbol but the node does not carry it as a synonym -> reject (guards wrong/stale gene)."""
        mock_req.return_value = {"NCBIGene:2688": _node(["SOMATROPIN", "Norditropin"], ["HGNC:4261"])}
        assert GeneSymbolResolver().resolve("GH1") is None

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_rejects_when_node_lacks_hgnc(self, mock_req):
        mock_req.return_value = {"NCBIGene:2688": _node(["SOMATROPIN", "GH1"], ["NCBIGene:2688", "UNII:X"])}
        assert GeneSymbolResolver().resolve("GH1") is None

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_accepts_lowercase_hgnc_prefix(self, mock_req):
        """The HGNC marker is matched case-insensitively, so a lower-cased prefix still verifies."""
        mock_req.return_value = {"NCBIGene:2688": _node(["SOMATROPIN", "GH1"], ["NCBIGene:2688", "hgnc:4261"])}
        assert GeneSymbolResolver().resolve("GH1") == "NCBIGene:2688"

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_get_nodes_error_returns_none(self, mock_req):
        mock_req.side_effect = RuntimeError("kestrel down")
        assert GeneSymbolResolver().resolve("GH1") is None

    @patch("biomapper2.core.gene_symbol_resolver.kestrel_request")
    def test_node_absent_returns_none(self, mock_req):
        mock_req.return_value = {}  # curie not in KG
        assert GeneSymbolResolver().resolve("GBA1") is None
