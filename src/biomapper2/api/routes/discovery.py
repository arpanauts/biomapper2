"""Discovery and health check endpoints."""

import logging

from fastapi import APIRouter, Request

from ..constants import API_VERSION
from ..kestrel_discovery import ALIASES, STATIC_FALLBACK
from ..models import (
    AnnotatorInfo,
    AnnotatorsResponse,
    EntityType,
    HealthResponse,
    VocabulariesResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Separate router for health check — never requires auth
health_router = APIRouter()


@health_router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    """Health check endpoint. Does not require authentication."""
    mapper = getattr(request.app.state, "mapper", None)
    mapper_error = getattr(request.app.state, "mapper_error", None)

    if mapper is not None:
        status = "healthy"
    elif mapper_error:
        status = f"degraded: {mapper_error}"
    else:
        status = "initializing"

    return HealthResponse(
        status=status,
        version=API_VERSION,
        mapper_initialized=mapper is not None,
    )


@router.get("/entity-types", response_model=list[EntityType], response_model_by_alias=True)
async def list_entity_types(request: Request) -> list[EntityType]:
    """List supported entity types with aliases and default vocabulary prefixes."""
    # Read presets from app.state (populated during lifespan startup)
    presets: dict[str, list[str]] = getattr(request.app.state, "entity_type_presets", None) or {}

    # If presets not loaded, build a minimal set from ALIASES + STATIC_FALLBACK
    if not presets:
        logger.warning("entity_type_presets not in app.state; using ALIASES + STATIC_FALLBACK")
        all_categories = set(ALIASES.values())
        for cat in STATIC_FALLBACK:
            all_categories.add(cat)
        presets = {cat: STATIC_FALLBACK.get(cat, []) for cat in all_categories}

    # Build reverse alias lookup: category -> list of alias names
    reverse_aliases: dict[str, list[str]] = {}
    for alias_name, category in ALIASES.items():
        reverse_aliases.setdefault(category, []).append(alias_name)

    # Create EntityType for each category in presets
    seen_categories: set[str] = set()
    result: list[EntityType] = []

    for category, prefix_list in sorted(presets.items()):
        seen_categories.add(category)
        aliases_for_cat = sorted(reverse_aliases.get(category, []))
        result.append(
            EntityType(
                type=category,
                aliases=aliases_for_cat if aliases_for_cat else None,
                default_prefixes=prefix_list if prefix_list else None,
            )
        )

    # Append biolink:NamedThing if not already present
    if "biolink:NamedThing" not in seen_categories:
        result.append(
            EntityType(
                type="biolink:NamedThing",
                aliases=["general", "untyped"],
                default_prefixes=[],
            )
        )

    return result


@router.get("/annotators", response_model=AnnotatorsResponse)
async def list_annotators(request: Request) -> AnnotatorsResponse:
    """List available annotators."""
    mapper = getattr(request.app.state, "mapper", None)

    if mapper is None:
        return AnnotatorsResponse(
            annotators=[
                AnnotatorInfo(
                    slug="kestrel_hybrid",
                    name="Kestrel Hybrid Search",
                    description="Combined text+vector search via Kestrel API",
                ),
                AnnotatorInfo(
                    slug="kestrel_text", name="Kestrel Text Search", description="Text-based search via Kestrel API"
                ),
                AnnotatorInfo(
                    slug="kestrel_vector",
                    name="Kestrel Vector Search",
                    description="Embedding-based search via Kestrel API",
                ),
                AnnotatorInfo(
                    slug="metabolomics_workbench",
                    name="Metabolomics Workbench",
                    description="RefMet annotations from Metabolomics Workbench",
                ),
            ]
        )

    annotators = []
    for slug, annotator in mapper.annotation_engine.annotator_registry.items():
        annotators.append(
            AnnotatorInfo(
                slug=slug,
                name=annotator.__class__.__name__,
                description=annotator.__doc__ or None,
            )
        )

    return AnnotatorsResponse(annotators=annotators)


@router.get("/vocabularies", response_model=VocabulariesResponse)
async def list_vocabularies(request: Request) -> VocabulariesResponse:
    """List supported vocabularies."""
    mapper = getattr(request.app.state, "mapper", None)

    if mapper is None:
        from ..models import VocabularyInfo

        common_vocabs = [
            VocabularyInfo(prefix="CHEBI", iri="http://purl.obolibrary.org/obo/CHEBI_"),
            VocabularyInfo(prefix="PUBCHEM.COMPOUND", iri="https://pubchem.ncbi.nlm.nih.gov/compound/"),
            VocabularyInfo(prefix="KEGG.COMPOUND", iri="https://www.kegg.jp/entry/"),
            VocabularyInfo(prefix="HMDB", iri="https://hmdb.ca/metabolites/"),
            VocabularyInfo(prefix="UNIPROT", iri="https://www.uniprot.org/uniprot/"),
        ]
        return VocabulariesResponse(vocabularies=common_vocabs, count=len(common_vocabs))

    from ...utils import ALIASES_PROP
    from ..models import VocabularyInfo

    vocab_info_map = mapper.normalizer.vocab_info_map
    vocab_validator_map = mapper.normalizer.vocab_validator_map

    vocabularies = []
    for key, info in vocab_info_map.items():
        prefix = info.get("prefix", key.upper())
        iri = info.get("iri")

        aliases = []
        if key in vocab_validator_map:
            aliases = vocab_validator_map[key].get(ALIASES_PROP, [])

        vocabularies.append(
            VocabularyInfo(
                prefix=prefix,
                iri=iri if iri else None,
                aliases=aliases,
            )
        )

    return VocabulariesResponse(
        vocabularies=sorted(vocabularies, key=lambda v: v.prefix),
        count=len(vocabularies),
    )
