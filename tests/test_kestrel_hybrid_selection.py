"""Unit tests for HGNC human-preference candidate selection in the hybrid-search annotator.

Mirrors the live Kestrel hybrid-search row shape verified 2026-06-15 (Unit 1 spike):
each row carries id/score/name/prefixes (plus equivalent_ids/neighbors_count, unused here).
Human gene rows carry "HGNC" in `prefixes`; orthologs and ENSEMBL transcripts never do.
Orthologs can share the same `name` as the human row, so the HGNC filter must come first.
"""

from biomapper2.core.annotators.kestrel_hybrid import KestrelHybridSearchAnnotator

select = KestrelHybridSearchAnnotator._select_result


def _row(node_id: str, score: float, name: str, prefixes: list[str], **extra):
    return {"id": node_id, "score": score, "name": name, "prefixes": prefixes, **extra}


# Realistic TNFRSF1A candidate set (abridged from the live spike): ortholog #1, human at #4.
TNFRSF1A_ROWS = [
    _row("NCBIGene:397020", 4.876, "TNFRSF1A", ["NCBIGene", "RGD", "UniProtKB", "ENSEMBL"]),
    _row("NCBIGene:406471", 3.333, "tnfrsf1a", ["NCBIGene", "UniProtKB", "ZFIN", "ENSEMBL"]),
    _row("NCBIGene:7132", 2.406, "TNFRSF1A", ["UMLS", "OMIM", "NCBIGene", "HGNC", "NCIT", "ENSEMBL"]),
    _row("ENSEMBL:ENST00000162749", 1.491, "TNFRSF1A-201", ["ENSEMBL"]),
]


class TestSelectResult:
    def test_human_below_top_is_selected(self):
        """Happy path: HGNC-bearing human row (#4, lower score) chosen over top-scored ortholog."""
        chosen, _ = select(TNFRSF1A_ROWS, "TNFRSF1A", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:7132"

    def test_human_at_top_is_selected(self):
        """Happy path: top-scored row already carries HGNC and matches the symbol -> chosen."""
        rows = [
            _row("NCBIGene:7132", 4.9, "TNFRSF1A", ["NCBIGene", "HGNC", "ENSEMBL"]),
            _row("NCBIGene:397020", 4.8, "TNFRSF1A", ["NCBIGene", "RGD"]),
        ]
        chosen, _ = select(rows, "TNFRSF1A", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:7132"

    def test_higher_scoring_paralog_not_chosen_over_queried_gene(self):
        """Edge (R7): a higher-scoring HGNC paralog must NOT beat the lower-scoring queried gene."""
        rows = [
            _row("NCBIGene:7133", 4.5, "TNFRSF1B", ["NCBIGene", "HGNC"]),  # paralog, higher score
            _row("NCBIGene:7132", 2.4, "TNFRSF1A", ["NCBIGene", "HGNC"]),  # queried gene
        ]
        chosen, _ = select(rows, "TNFRSF1A", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:7132"

    def test_no_hgnc_falls_back_to_top_score(self):
        """Edge: no HGNC-bearing row -> honest fallback to the top-scored candidate."""
        rows = [
            _row("NCBIGene:397020", 4.8, "TNFRSF1A", ["NCBIGene", "RGD"]),
            _row("NCBIGene:406471", 3.3, "tnfrsf1a", ["NCBIGene", "ZFIN"]),
        ]
        chosen, _ = select(rows, "TNFRSF1A", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:397020"

    def test_alias_query_still_picks_human(self):
        """Edge: HGNC row exists but its name doesn't equal the (alias) query -> best human, not ortholog."""
        rows = [
            _row("NCBIGene:397020", 4.8, "TNFRSF1A", ["NCBIGene", "RGD"]),  # ortholog, top score
            _row("NCBIGene:7132", 2.4, "TNFRSF1A", ["NCBIGene", "HGNC"], synonyms=["TNFR1", "CD120a"]),
        ]
        chosen, _ = select(rows, "CD120a", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:7132"

    def test_prefer_human_false_returns_top_score(self):
        """Edge: prefer_human disabled -> legacy top-1 behavior regardless of HGNC."""
        chosen, _ = select(TNFRSF1A_ROWS, "TNFRSF1A", prefer_human=False)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:397020"

    def test_empty_candidate_list_returns_none(self):
        """Edge: empty list -> None, no exception."""
        assert select([], "TNFRSF1A", prefer_human=True)[0] is None

    def test_missing_keys_do_not_raise(self):
        """Edge: rows missing `prefixes`/`score` keys are tolerated (treated as non-human, fallback)."""
        rows = [{"id": "NCBIGene:1", "name": "X"}, {"id": "NCBIGene:2", "name": "X", "score": 1.0}]
        chosen, _ = select(rows, "X", prefer_human=True)
        assert chosen is not None
        assert chosen["id"] == "NCBIGene:1"  # first row, honest fallback (no HGNC anywhere)
