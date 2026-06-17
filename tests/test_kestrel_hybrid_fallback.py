"""Tests for the gene-symbol fallback wiring in the hybrid annotator.

These exercise the real `_select_result` (so the miss/match signal is validated, not mocked) and a
mocked resolver, via the annotator's cache path so no Kestrel search call is made.
"""

from unittest.mock import MagicMock

from biomapper2.core.annotators.kestrel_hybrid import KestrelHybridSearchAnnotator


def _row(node_id, score, name, prefixes):
    return {"id": node_id, "score": score, "name": name, "prefixes": prefixes}


def _annotate(rows, term, prefer_human=True, resolver_returns: str | None = "NCBIGene:2688"):
    """Run get_annotations via the cache path with a mocked resolver; return (assigned, resolver_mock)."""
    ann = KestrelHybridSearchAnnotator()
    ann._resolver = MagicMock()
    ann._resolver.resolve.return_value = resolver_returns
    assigned = ann.get_annotations(
        {"name": term}, "name", "biolink:Gene", prefer_human=prefer_human, cache={term: rows}
    )
    return assigned[ann.slug], ann._resolver


class TestFallbackWiring:
    def test_ortholog_miss_uses_resolver(self):
        """Only a non-HGNC ortholog returned -> resolver fires -> resolved human node chosen."""
        rows = [_row("NCBIGene:403795", 4.8, "GH1", ["NCBIGene", "RGD"])]
        annotations, resolver = _annotate(rows, "GH1")
        assert "2688" in annotations.get("NCBIGene", {})
        assert "403795" not in annotations.get("NCBIGene", {})
        resolver.resolve.assert_called_once_with("GH1")
        assert annotations["NCBIGene"]["2688"].get("resolved_via") == "symbol_fallback"

    def test_paralog_hgnc_no_symbol_match_uses_resolver(self):
        """Real _select_result returns a higher-scoring HGNC paralog (no symbol match) -> still a miss."""
        rows = [
            _row("NCBIGene:7133", 4.5, "TNFRSF1B", ["NCBIGene", "HGNC"]),  # HGNC but wrong gene
            _row("NCBIGene:403795", 3.0, "GH1", ["NCBIGene", "RGD"]),
        ]
        annotations, resolver = _annotate(rows, "GH1")  # query GH1; no row symbol-matches GH1
        resolver.resolve.assert_called_once_with("GH1")
        assert "2688" in annotations.get("NCBIGene", {})
        assert "7133" not in annotations.get("NCBIGene", {})

    def test_genuine_hit_skips_resolver(self):
        """An HGNC row that exact-symbol-matches the query is a hit -> resolver not called."""
        rows = [
            _row("NCBIGene:403795", 4.8, "GH1", ["NCBIGene", "RGD"]),  # ortholog, top score
            _row("NCBIGene:2688", 2.4, "GH1", ["NCBIGene", "HGNC"]),  # human, HGNC + symbol match
        ]
        annotations, resolver = _annotate(rows, "GH1")
        resolver.resolve.assert_not_called()
        assert "2688" in annotations.get("NCBIGene", {})
        assert "resolved_via" not in annotations["NCBIGene"]["2688"]

    def test_non_curated_miss_keeps_ortholog(self):
        """Resolver returns None (non-curated symbol) -> honest ortholog fallback preserved."""
        rows = [_row("NCBIGene:999", 4.8, "FOO", ["NCBIGene", "RGD"])]
        annotations, resolver = _annotate(rows, "FOO", resolver_returns=None)
        resolver.resolve.assert_called_once_with("FOO")
        assert "999" in annotations.get("NCBIGene", {})

    def test_prefer_human_false_skips_resolver(self):
        rows = [_row("NCBIGene:403795", 4.8, "GH1", ["NCBIGene", "RGD"])]
        annotations, resolver = _annotate(rows, "GH1", prefer_human=False)
        resolver.resolve.assert_not_called()
        assert "403795" in annotations.get("NCBIGene", {})

    def test_fallback_disabled_skips_resolver(self, monkeypatch):
        monkeypatch.setattr("biomapper2.core.annotators.kestrel_hybrid.GENE_SYMBOL_FALLBACK_ENABLED", False)
        rows = [_row("NCBIGene:403795", 4.8, "GH1", ["NCBIGene", "RGD"])]
        annotations, resolver = _annotate(rows, "GH1")
        resolver.resolve.assert_not_called()
        assert "403795" in annotations.get("NCBIGene", {})

    def test_empty_results_uses_resolver(self):
        """No candidates at all -> resolver attempted; if it resolves, that node is used."""
        annotations, resolver = _annotate([], "GH1")
        resolver.resolve.assert_called_once_with("GH1")
        assert "2688" in annotations.get("NCBIGene", {})
