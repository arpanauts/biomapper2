import logging
from typing import Any, cast

import pandas as pd

from ...config import HUMAN_MARKER_PREFIXES, HYBRID_SEARCH_LIMIT, KESTREL_BATCH_SIZE_SEARCH
from ...utils import AssignedIDsDict, kestrel_request, text_is_not_empty
from .base import BaseAnnotator


class KestrelHybridSearchAnnotator(BaseAnnotator):

    slug = "kestrel-hybrid-search"

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
            chosen = self._select_result(term_results, search_term, prefer_human)
            if chosen is not None:
                node_id = chosen["id"]
                score = chosen["score"]
                vocab, local_id = node_id.split(":", 1)
                annotations.setdefault(vocab, {})[local_id] = {"score": score}

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
    def _select_result(term_results: list[dict] | None, search_term: str, prefer_human: bool) -> dict | None:
        """Select one candidate row from a hybrid-search result list.

        Two-tier human preference (finalized from the 2026-06-15 live spike):
        1. Filter to human (HGNC-bearing) rows; if none, fall back to the top-scored candidate.
        2. Among human rows, prefer those whose symbol matches the query (``name`` or a synonym);
           if none match, keep all human rows (avoids over-rejecting alias queries to an ortholog).
        3. Return the highest-scoring row of that pool.

        The HGNC filter must precede the symbol match because orthologs share the human row's ``name``
        (same symbol, different species) — HGNC separates species, the symbol match picks the right gene.
        Returns None for an empty/None result list.
        """
        if not term_results:
            return None
        if not prefer_human:
            return term_results[0]

        human = [r for r in term_results if HUMAN_MARKER_PREFIXES & set(r.get("prefixes", []))]
        if not human:
            return term_results[0]

        exact = [r for r in human if KestrelHybridSearchAnnotator._symbol_matches(r, search_term)]
        pool = exact if exact else human
        return max(pool, key=lambda r: r.get("score", 0))

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
