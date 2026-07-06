"""
Configuration settings for biomapper2.

Customize these values to change API endpoints, model versions, and logging behavior.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # Load environmental variables (secrets)


# Set up our general cache directory (e.g., for requests cache, biolink)
PROJECT_ROOT = Path(__file__).parents[2]
CACHE_DIR = PROJECT_ROOT / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# KG API configuration — override via KESTREL_API_URL in .env
KESTREL_API_URL = os.getenv("KESTREL_API_URL", "https://kestrel.nathanpricelab.com/api")

# Biolink model version
BIOLINK_VERSION_DEFAULT = "4.2.5"

# Level of logging messages to display (DEBUG, INFO, WARNING, ERROR, or CRITICAL)
LOG_LEVEL = "INFO"

# Secrets (from environment variables)
_kestrel_api_key: str | None = None


def get_kestrel_api_key() -> str:
    global _kestrel_api_key
    if _kestrel_api_key is None:
        _kestrel_api_key = os.getenv("KESTREL_API_KEY")
        if not _kestrel_api_key:
            raise ValueError("KESTREL_API_KEY environment variable is not set")
    return _kestrel_api_key


# Batching for Kestrel API requests (to prevent timeouts on large datasets)
KESTREL_BATCHING_ENABLED = True  # Set to False to disable batching (for performance testing)
KESTREL_BATCH_SIZE_SEARCH = 1000  # For text-search, vector-search, hybrid-search
KESTREL_BATCH_SIZE_CANONICALIZE = 2000  # For canonicalize endpoint

# Human-preference re-ranking for gene/protein resolution (see docs/plans HGNC plan).
# When prefer_human is active, hybrid-search retrieves this many candidates (instead of 1) so the
# human node — which often ranks below the wrong-species ortholog — is actually returned. Live spike
# (2026-06-15) found recoverable human nodes at rank ~#4; 20 gives ample margin.
HYBRID_SEARCH_LIMIT = 20
# Human-only CURIE prefixes. HGNC assigns IDs only to human genes, so its presence in a hybrid-search
# row's `prefixes` marks the human node. Any prefix added here must itself be human-exclusive.
HUMAN_MARKER_PREFIXES = {"HGNC"}

# Kill switch for the curated gene-symbol fallback bridge (see core/gene_symbol_resolver.py). When True
# (default), gene/protein resolution misses for the curated drug-conflated symbols are resolved via the
# deterministic non-search fallback. Set False to disable the bridge without a code revert.
GENE_SYMBOL_FALLBACK_ENABLED = True

# Per-category preferred (canonical) namespace prefixes for the prefer_canonical re-ranking. Within a
# Biolink category, hybrid-search ranks across all namespaces at once, so a non-canonical same-text node
# (UMLS/ICD/KEGG/PANTHER) frequently outranks the canonical one. These prefixes mark the canonical node so
# the annotator can prefer it (see core/annotators/kestrel_hybrid.py:_select_canonical). Keys are Biolink
# categories; the engine expands each via get_descendants so subcategories inherit the policy. Gene/protein
# are intentionally absent — they use HUMAN_MARKER_PREFIXES / prefer_human instead.
#
# Prefix strings are the *actual* Kestrel KG prefixes, verified live 2026-06-18 against hybrid-search rows
# (e.g. RefMet is "RM", not "REFMET"). A wrong string is a silent no-op (the filter matches nothing).
CATEGORY_PREFERRED_NAMESPACES: dict[str, set[str]] = {
    "biolink:SmallMolecule": {"CHEBI", "HMDB", "RM"},
    "biolink:Disease": {"MONDO"},
}
