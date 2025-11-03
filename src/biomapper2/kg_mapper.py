import copy
from typing import Dict, Any

from .annotator import annotate
from .normalizer import normalize
from .linker import link
from .resolver import resolve


def map_to_kg(entity: Dict[str, Any]) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)  # Use a copy to avoid editing input item

    annotate(entity)
    normalize(entity)
    link(entity)
    resolve(entity)

    return entity
