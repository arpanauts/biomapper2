import logging
from typing import Any, cast

import pandas as pd

from ...config import (
    GENE_SYMBOL_FALLBACK_ENABLED,
    HUMAN_MARKER_PREFIXES,
    HYBRID_SEARCH_LIMIT,
    KESTREL_BATCH_SIZE_SEARCH,
)
from ...utils import AssignedIDsDict, kestrel_request, text_is_not_empty
from ..gene_symbol_resolver import GeneSymbolResolver
from .base import BaseAnnotator

# Score assigned to a node recovered by the deterministic symbol fallback. Modest and fixed: the result
# is a verified identity match, but it bypassed competitive search, so it must not be reported as a top
# search hit. The `resolved_via` provenance marker is the authoritative signal, not this score.
_FALLBACK_SCORE = 1.0


class KestrelHybridSearchAnnotator(BaseAnnotator):

    slug = "kestrel-hybrid-search"

    def __init__(self) -> None:
        # Annotator-owned resolver (arg-free construction preserves the registry pattern; no network here).
        self._resolver = GeneSymbolResolver()

    def get_annotations(
        self,
        entity: dict | pd.Series,
        name_field: str,
        category: str,
        prefixes: list[str] | None = None,
        prefer_human: bool = True,
        cache: dict | None = None,
    ) -> AssignedIDsDict:
        """Implements BaseAnnotator.get_annotations.

        When ``prefer_human`` is True the annotator retrieves multiple candidates and selects the
        human (HGNC-bearing) one that matches the queried symbol, falling back to the top-scored
        candidate on a miss (see ``_select_result``). When False it keeps the legacy top-1 behavior.
        The engine passes the *applicability-gated* value (True only for gene/protein categories).
        """

        # Extract the value to search
        search_term = entity.get(name_field)
        if text_is_not_empty(search_term):
            # Use cache if available, otherwise make API call
            if cache:
                term_results = cache.get(search_term)
            else:
                limit = HYBRID_SEARCH_LIMIT if prefer_human else 1
                results = self._kestrel_hybrid_search(search_term, category, prefixes, limit=limit)
                term_results = results[search_term]

            annotations: dict[str, dict[str, dict[str, Any]]] = {}
            chosen, matched = self._select_result(term_results, search_term, prefer_human)

            # Miss path: no HGNC + exact-symbol match was found among the search rows (ortholog fallback,
            # empty results, or a best-HGNC paralog). For the curated drug-conflated symbols, the human
            # node is unreachable by search, so resolve it deterministically (non-search) and verify.
            if prefer_human and GENE_SYMBOL_FALLBACK_ENABLED and not matched:
                resolved_curie = self._resolver.resolve(search_term)
                if resolved_curie is not None:
                    chosen = {"id": resolved_curie, "score": _FALLBACK_SCORE, "resolved_via": "symbol_fallback"}

            if chosen is not None:
                node_id = chosen["id"]
                score = chosen["score"]
                vocab, local_id = node_id.split(":", 1)
                metadata: dict[str, Any] = {"score": score}
                if chosen.get("resolved_via"):
                    metadata["resolved_via"] = chosen["resolved_via"]
                annotations.setdefault(vocab, {})[local_id] = metadata

            return {self.slug: annotations}
        else:
            # This entity didn't have a name, so we can't use this annotator on it
            return dict()

    def get_annotations_bulk(
        self,
        entities: pd.DataFrame,
        name_field: str,
        category: str,
        prefixes: list[str] | None = None,
        prefer_human: bool = True,
    ) -> pd.Series:  # Series of AssignedIDsDicts
        """Implements BaseAnnotator.get_annotations_bulk"""

        # Filter out any empty/NaN entity names
        search_terms = [t for t in entities[name_field].tolist() if text_is_not_empty(t)]

        logging.info(f"Getting hybrid search results from Kestrel API for {len(entities)} entities")
        # Only enlarge the candidate window when human-preference is active (keeps payloads small for
        # metabolite/other bulk jobs where the re-ranking does not apply).
        limit = HYBRID_SEARCH_LIMIT if prefer_human else 1
        results = self._kestrel_hybrid_search(search_terms, category, prefixes, limit=limit)

        # Annotate each entity using the results from the bulk request. The internal re-dispatch MUST
        # forward prefer_human, otherwise the bulk path would silently use the get_annotations default.
        assigned_ids_col = entities.apply(
            self.get_annotations,
            axis=1,
            cache=results,
            name_field=name_field,
            category=category,
            prefixes=prefixes,
            prefer_human=prefer_human,
        )

        return cast(pd.Series, assigned_ids_col)

    # ----------------------------------------- Helper methods ----------------------------------------------- #

    @staticmethod
    def _select_result(
        term_results: list[dict] | None, search_term: str, prefer_human: bool
    ) -> tuple[dict | None, bool]:
        """Select one candidate row, and report whether it is a genuine human-gene match.

        Returns ``(chosen_row, matched)`` where ``matched`` is True only when ``chosen_row`` is an
        HGNC-bearing row that exact-symbol-matches the query. ``matched`` is False for an empty result,
        the legacy top-1, the ortholog fallback, and the best-HGNC-but-no-symbol-match (paralog) case —
        all of which the caller treats as a miss eligible for the deterministic symbol fallback.

        Two-tier human preference (finalized from the 2026-06-15 live spike):
        1. Filter to human (HGNC-bearing) rows; if none, fall back to the top-scored candidate.
        2. Among human rows, prefer those whose symbol matches the query (``name`` or a synonym). A
           symbol-matched pick is the only genuine "match"; the no-symbol-match fallback is not.
        3. Return the highest-scoring row of the chosen pool.

        The HGNC filter must precede the symbol match because orthologs share the human row's ``name``
        (same symbol, different species) — HGNC separates species, the symbol match picks the right gene.
        """
        if not term_results:
            return None, False
        if not prefer_human:
            return term_results[0], False

        human = [r for r in term_results if HUMAN_MARKER_PREFIXES & set(r.get("prefixes") or [])]
        if not human:
            return term_results[0], False

        exact = [r for r in human if KestrelHybridSearchAnnotator._symbol_matches(r, search_term)]
        if exact:
            return max(exact, key=lambda r: r.get("score", 0)), True
        # HGNC rows exist but none symbol-match the query (e.g. a paralog) — not a genuine match.
        return max(human, key=lambda r: r.get("score", 0)), False

    @staticmethod
    def _symbol_matches(row: dict, search_term: str) -> bool:
        """True if the row's ``name`` equals the query (case-insensitive) or the query is a synonym."""
        term = str(search_term).strip().lower()
        if str(row.get("name", "")).strip().lower() == term:
            return True
        return any(str(s).strip().lower() == term for s in row.get("synonyms", []) or [])

    @staticmethod
    def _kestrel_hybrid_search(
        search_text: str | list[str], category: str, prefixes: list[str] | None, limit: int = 10
    ) -> dict[str, list[dict]]:
        """Call Kestrel hybrid search endpoint (with batching for large lists)."""
        search_list = [search_text] if isinstance(search_text, str) else list(search_text)

        results = kestrel_request(
            method="POST",
            endpoint="hybrid-search",
            batch_field="search_text",
            batch_items=search_list,
            batch_size=KESTREL_BATCH_SIZE_SEARCH,
            json={"limit": limit, "category_filter": category, "prefix_filter": prefixes},
        )
        # Filter out very low-scoring results (hybrid search scores range from 0-5)
        return {s: [match for match in matches if match["score"] >= 0.5] for s, matches in results.items()}
