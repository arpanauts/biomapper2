"""Tests for the canonical-namespace selection in the hybrid annotator (prefer_canonical path).

The `_select_canonical` cases mirror live Kestrel `hybrid-search` data captured 2026-06-18: the canonical
node (CHEBI/HMDB/RM for metabolites, MONDO for disease) routinely scores well *below* a conflated
non-canonical node, so there is deliberately no score-margin guard — the namespace filter plus an identity
match is the discriminator. The wiring cases run through the annotator's cache path so no network call is made.
"""

from unittest.mock import patch

from biomapper2.core.annotators.kestrel_hybrid import KestrelHybridSearchAnnotator

MET = {"CHEBI", "HMDB", "RM"}


def _row(node_id, score, name, synonyms=None):
    return {"id": node_id, "score": score, "name": name, "synonyms": synonyms or []}


class TestSelectCanonical:
    def test_identity_match_below_noncanonical_top(self):
        """kynurenine: CHEBI node name-matches the query though it scores far below the UMLS top hit."""
        rows = [
            _row("UMLS:C0022818", 4.89, "Kynurenine"),
            _row("CHEBI:28683", 2.50, "kynurenine"),
            _row("CHEBI:16946", 2.49, "L-kynurenine"),
        ]
        chosen, is_canonical = KestrelHybridSearchAnnotator._select_canonical(rows, MET, "kynurenine")
        assert chosen is not None and chosen["id"] == "CHEBI:28683" and is_canonical

    def test_name_mismatch_takes_top_scored_canonical(self):
        """CML: no MONDO name-matches the colloquial query -> the top-scored MONDO is chosen."""
        rows = [
            _row("KEGG:05220", 4.86, "Chronic myeloid leukemia"),
            _row("MONDO:0011996", 2.50, "chronic myelogenous leukemia, BCR-ABL1 positive"),
            _row("MONDO:0004643", 1.50, "myeloid leukemia"),
        ]
        chosen, is_canonical = KestrelHybridSearchAnnotator._select_canonical(
            rows, {"MONDO"}, "chronic myeloid leukemia"
        )
        assert chosen is not None and chosen["id"] == "MONDO:0011996" and is_canonical

    def test_lowercase_kg_prefix_still_matches(self):
        """A differently-cased KG namespace must still be recognized as canonical (case-insensitive filter)."""
        rows = [_row("UMLS:X", 4.0, "thing"), _row("chebi:28683", 2.0, "thing")]
        chosen, is_canonical = KestrelHybridSearchAnnotator._select_canonical(rows, MET, "thing")
        assert chosen is not None and chosen["id"] == "chebi:28683" and is_canonical

    def test_fallback_paths_are_not_canonical(self):
        """Empty pool -> honest top-scored fallback (not canonical); empty results -> (None, False)."""
        rows = [_row("UMLS:X", 3.0, "foo"), _row("CHV:Y", 2.0, "foo")]
        chosen, is_canonical = KestrelHybridSearchAnnotator._select_canonical(rows, MET, "foo")
        assert chosen is not None and chosen["id"] == "UMLS:X" and not is_canonical
        assert KestrelHybridSearchAnnotator._select_canonical([], MET, "foo") == (None, False)

    def test_homonym_disambiguated_by_name_or_synonym(self):
        """Multiple CHEBI rows; the one matching the query by name (or synonym) wins over higher-scored ones."""
        rows = [
            _row("CHEBI:29987", 1.44, "glutamate(2-)"),
            _row("CHEBI:14321", 1.44, "glutamate(1-)", synonyms=["glutamate"]),  # synonym match
        ]
        chosen, _ = KestrelHybridSearchAnnotator._select_canonical(rows, MET, "glutamate")
        assert chosen is not None and chosen["id"] == "CHEBI:14321"


def _annotate(rows, term, preferred_prefixes):
    ann = KestrelHybridSearchAnnotator()
    return ann.get_annotations(
        {"name": term},
        "name",
        "biolink:SmallMolecule",
        prefer_human=False,
        preferred_prefixes=preferred_prefixes,
        cache={term: rows},
    )[ann.slug]


class TestCanonicalWiring:
    def test_canonical_chosen_and_tagged(self):
        rows = [_row("UMLS:C0022818", 4.89, "Kynurenine"), _row("CHEBI:28683", 2.50, "kynurenine")]
        annotations = _annotate(rows, "kynurenine", MET)
        assert "28683" in annotations.get("CHEBI", {})
        assert annotations["CHEBI"]["28683"].get("resolved_via") == "canonical_preference"
        assert "C0022818" not in annotations.get("UMLS", {})

    def test_no_canonical_keeps_top_untagged(self):
        rows = [_row("UMLS:X", 3.0, "foo")]
        annotations = _annotate(rows, "foo", MET)
        assert "X" in annotations.get("UMLS", {})
        assert "resolved_via" not in annotations["UMLS"]["X"]

    def test_bulk_forwards_preferred_prefixes(self):
        """get_annotations_bulk must forward preferred_prefixes to the per-row re-dispatch (else a no-op)."""
        import pandas as pd

        rows = [_row("UMLS:C0022818", 4.89, "Kynurenine"), _row("CHEBI:28683", 2.50, "kynurenine")]
        ann = KestrelHybridSearchAnnotator()
        with patch.object(ann, "_kestrel_hybrid_search", return_value={"kynurenine": rows}):
            out = ann.get_annotations_bulk(
                pd.DataFrame({"name": ["kynurenine"]}),
                "name",
                "biolink:SmallMolecule",
                prefer_human=False,
                preferred_prefixes=MET,
            )
        assert "28683" in out.iloc[0][ann.slug].get("CHEBI", {})
