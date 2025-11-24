"""
Entity annotation module for assigning ontology local IDs.

Queries external APIs or uses other creative approaches to retrieve additional identifiers for biological entities.
"""
import logging
from copy import deepcopy
from typing import Dict, Any, List, Set, Optional, Literal

import pandas as pd

from .annotators.kestrel_text import KestrelTextSearchAnnotator
from ..utils import AssignedIDsDict


def annotate(item: pd.Series | Dict[str, Any] | pd.DataFrame,
             name_field: str,
             provided_id_fields: List[str],
             entity_type: str,
             mode: Literal['all', 'missing', 'none'] = 'missing') -> AssignedIDsDict | pd.Series:
    """
    Annotate entity with additional local IDs, obtained using various internal or external methods.

    Args:
        item: Entity or entities to annotate
        name_field: Field containing entity name
        provided_id_fields: Fields containing existing IDs
        entity_type: Type of entity (e.g., 'metabolite', 'protein')
        mode: When to annotate
            - 'all': Annotate all entities
            - 'missing': Only annotate entities without provided_ids (default)
            - 'none': Skip annotation entirely (returns empty)

    Returns:
        AssignedIDsDict for single entity, pd.Series of AssignedIDsDict for DataFrame
    """
    # Validate mode
    valid_modes = {'all', 'missing', 'none'}
    if mode not in valid_modes:
        raise ValueError(f"Invalid mode '{mode}'. Must be one of: {valid_modes}")

    logging.debug(f"Beginning annotation step..")
    entity_type_cleaned = ''.join(c for c in entity_type.lower() if c.isalpha())

    # Skip annotation if user requested it
    if mode == 'none':
        logging.debug(f"Skipping all annotation since mode={mode}")
        return _get_empty_assigned_ids(item)

    # Figure out which annotators to use (PLACEHOLDER - need to adjust heuristics here for mvp)
    annotators = []
    if entity_type_cleaned in {'metabolite', 'smallmolecule', 'lipid'}:
        pass  # TODO: plug in metabolomics workbench API here..
    if not annotators:
        # Back up to using a text search (this is a PLACEHOLDER, should not be fallback long-term)
        annotators.append(KestrelTextSearchAnnotator())

    if annotators:
        logging.debug(f"Using annotators: {annotators}")
    else:
        logging.warning(f"Did not identify any annotators to use for input item. Proceeding without assigned IDs.")
        return _get_empty_assigned_ids(item)

    # Get annotations using selected annotators, handling dataset input vs. single-entity input separately
    if isinstance(item, pd.DataFrame):
        # An entire dataset was passed in
        if mode == 'missing':
            # Identify rows that need annotation (no provided_ids)
            has_ids_mask = item[provided_id_fields].notna().any(axis=1)
            needs_annotation_mask = ~has_ids_mask
            items_to_annotate = item[needs_annotation_mask]
            logging.info(f"Mode is 'missing': annotating {needs_annotation_mask.sum()} of {len(item)} rows")
        else:  # mode == 'all'
            items_to_annotate = item
            needs_annotation_mask = pd.Series([True] * len(item), index=item.index)

        # Initialize results column with empty dicts for all rows
        assigned_ids_col = pd.Series([{} for _ in range(len(item))], index=item.index)

        # Only annotate rows that need it
        if not items_to_annotate.empty:
            results_subset = pd.Series([{} for _ in range(len(items_to_annotate))], index=items_to_annotate.index)

            for annotator in annotators:
                prepared_df = annotator.prepare(items_to_annotate, provided_id_fields)
                annotations_col = annotator.get_annotations_bulk(prepared_df, name_field)
                results_subset = pd.Series(
                    [_merge_nested_dicts(d1, d2) for d1, d2 in zip(results_subset, annotations_col)],
                    index=results_subset.index
                )

            # Merge partial results (subset that need annotation) back into full results
            assigned_ids_col[needs_annotation_mask] = results_subset

        return assigned_ids_col
    else:
        # A single entity was passed in

        # If user requested it, skip entities that have any provided IDs
        if mode == 'missing':
            has_provided_ids = any(pd.notna(item.get(field)) for field in provided_id_fields)
            if has_provided_ids:
                logging.debug(f"Entity has provided_ids and mode={mode}, skipping annotation")
                return _get_empty_assigned_ids(item)

        # Otherwise get assigned IDs for the entity
        assigned_ids = dict()  # All annotations will be merged into this
        for annotator in annotators:
            prepared_entity = annotator.prepare(item, provided_id_fields)
            entity_annotations = annotator.get_annotations(prepared_entity, name_field)
            assigned_ids = _merge_nested_dicts(assigned_ids, entity_annotations)

        return assigned_ids


def _merge_nested_dicts(d1: AssignedIDsDict, d2: AssignedIDsDict) -> AssignedIDsDict:
    """
    Merge two nested dicts with structure:
    Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]

    Structure: {annotator: {vocabulary: {id: result_metadata_dict}}}
    """
    result = deepcopy(d1)

    for annotator, vocab_dict in d2.items():
        if annotator in result:
            # Annotator exists, merge vocabularies
            for vocab, id_dict in vocab_dict.items():
                if vocab in result[annotator]:
                    # Vocabulary exists, merge IDs
                    for id_str, result_metadata in id_dict.items():
                        if id_str in result[annotator][vocab]:
                            # ID exists, update/merge the metadata dict
                            result[annotator][vocab][id_str].update(result_metadata)
                        else:
                            # New ID
                            result[annotator][vocab][id_str] = result_metadata
                else:
                    # New vocabulary
                    result[annotator][vocab] = deepcopy(id_dict)
        else:
            # New annotator
            result[annotator] = deepcopy(vocab_dict)

    return result


def _get_empty_assigned_ids(item: pd.Series | Dict[str, Any] | pd.DataFrame) -> AssignedIDsDict | pd.Series:
    if isinstance(item, pd.DataFrame):
        return pd.Series([{} for _ in range(len(item))], index=item.index)
    else:
        return {}
