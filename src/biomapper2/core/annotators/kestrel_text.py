import logging
from collections import defaultdict
from typing import Any

import pandas as pd

from ...utils import AssignedIDsDict, kestrel_request, text_is_not_empty
from .base import BaseAnnotator


class KestrelTextSearchAnnotator(BaseAnnotator):

    slug = "kestrel-text-search"

    def get_annotations(self, entity: dict | pd.Series, name_field: str, cache: dict | None = None) -> AssignedIDsDict:
        """Get annotations via Kestrel text search."""

        # Extract the value to search
        search_term = entity.get(name_field)
        if text_is_not_empty(search_term):
            # Use cache if available, otherwise make API call
            if cache:
                term_results = cache.get(search_term)
            else:
                term_results = self._kestrel_text_search(search_term, limit=1)

            annotations: dict[str, dict[str, dict[str, Any]]] = {}
            if term_results:
                first_result = term_results[0]
                node_id = first_result["id"]
                score = first_result["score"]
                vocab, local_id = node_id.split(":", 1)
                annotations.setdefault(vocab, {})[local_id] = {"score": score}

            return {self.slug: annotations}
        else:
            # This entity didn't have a name, so we can't use this annotator on it
            return dict()

    def get_annotations_bulk(self, entities: pd.DataFrame, name_field: str) -> pd.Series:  # Series of AssignedIDsDicts
        """Get annotations for multiple entities with bulk optimization."""

        search_terms = entities[name_field].tolist()

        logging.info(f"Getting text search results from Kestrel API for {len(entities)} entities")
        results = self._kestrel_text_search(search_terms, limit=1)

        # Annotate each entity using the results from the bulk request
        assigned_ids_col = entities.apply(self.get_annotations, axis=1, cache=results, name_field=name_field)

        return assigned_ids_col

    # ----------------------------------------- Helper methods ----------------------------------------------- #

    @staticmethod
    def _kestrel_text_search(query: str | list[str], limit: int = 10) -> list[dict]:
        """Call Kestrel text search endpoint."""
        return kestrel_request("POST", "text-search", json={"search_text": query, "limit": limit})
