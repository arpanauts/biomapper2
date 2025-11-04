import copy
from typing import Dict, Any

from .annotator import annotate
from .normalizer import Normalizer
from .linker import link
from .resolver import resolve


def map_to_kg(entity: Dict[str, Any]) -> Dict[str, Any]:
    entity = copy.deepcopy(entity)  # Use a copy to avoid editing input item
    normalizer = Normalizer(biolink_version='4.2.5')  # Instantiate the ID normalizer (should only be done once, up front)

    # Perform all mapping steps
    annotate(entity)
    normalizer.normalize(entity)
    link(entity)
    resolve(entity)

    return entity
