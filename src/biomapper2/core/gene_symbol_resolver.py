"""Curated, non-search fallback for human gene nodes that Kestrel search cannot surface.

A small set of human genes whose protein product is a marketed therapeutic are conflated by the
upstream Translator/Babel layer into a single node named for the drug (e.g. GH1 -> the SOMATROPIN
node). The node still carries the gene symbol as a synonym and an HGNC equivalent, but it never ranks
for the gene symbol in any Kestrel search modality, so `prefer_human` re-ranking can never reach it.

This resolver is a deterministic, non-search bridge: for the curated symbols only, it returns the
canonical human NCBIGene CURIE, accepting it only after `/get-nodes` confirms the node carries the
queried symbol as a synonym AND an HGNC equivalent (so it cannot inject a wrong-but-human gene). It is
a no-op for every other symbol. This is a temporary measure; the durable fix is upstream (Kestrel-side
exact-symbol retrieval / de-conflation). See docs/plans/2026-06-17-001-feat-gene-symbol-fallback-resolver-plan.md.
"""

from ..config import KESTREL_BATCH_SIZE_CANONICALIZE
from ..utils import kestrel_request

# Verified 2026-06-16: each of these human gene nodes carries its gene symbol as a synonym and an
# HGNC equivalent, yet is unreachable by symbol across hybrid/text/vector search (drug-conflation).
CURATED_GENE_SYMBOL_TO_CURIE = {
    "GH1": "NCBIGene:2688",
    "CALCA": "NCBIGene:796",
    "POMC": "NCBIGene:5443",
    "CRH": "NCBIGene:1392",
    "CTLA4": "NCBIGene:1493",
    "GBA1": "NCBIGene:2629",
}

# Case-folded lookup so queries match regardless of case.
_CURATED = {symbol.casefold(): curie for symbol, curie in CURATED_GENE_SYMBOL_TO_CURIE.items()}


class GeneSymbolResolver:
    """Resolve a curated gene symbol to its HGNC-verified human NCBIGene CURIE (or None)."""

    def resolve(self, symbol: str | None) -> str | None:
        """Return the canonical human NCBIGene CURIE for a curated symbol, else None.

        Returns None (a no-op) for any non-curated symbol, and rejects a curated symbol whose node
        does not carry the queried symbol as a synonym or lacks an HGNC equivalent — never fabricates
        and never returns a different human gene.
        """
        if not symbol:
            return None
        key = str(symbol).strip().casefold()
        curie = _CURATED.get(key)
        if curie is None:
            return None  # no-op for everything outside the curated set

        try:
            nodes = kestrel_request(
                method="POST",
                endpoint="get-nodes",
                batch_field="curies",
                batch_items=[curie],
                batch_size=KESTREL_BATCH_SIZE_CANONICALIZE,
                json={"slim": False, "truncate_long_fields": False},
            )
        except Exception:
            return None  # honest fallback on any Kestrel error

        node = nodes.get(curie) if isinstance(nodes, dict) else None
        if not isinstance(node, dict):
            return None

        # Verify identity (queried symbol present as a synonym), not just humanity (HGNC present).
        synonyms = {str(s).strip().casefold() for s in (node.get("synonyms") or [])}
        if key not in synonyms:
            return None
        if not any(str(e).startswith("HGNC:") for e in (node.get("equivalent_ids") or [])):
            return None

        return curie
