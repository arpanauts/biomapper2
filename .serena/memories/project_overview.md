# biomapper2 - Project Overview

## Purpose
biomapper2 is a unified toolkit for multiomics data harmonization. It maps biological entities (metabolites, proteins, etc.) to knowledge graph nodes through a four-step pipeline.

## Architecture Pipeline
```
Input Entity → Annotation → Normalization → Linking → Resolution → Mapped Entity
```

### Pipeline Components (all in `src/biomapper2/core/`)

1. **Annotation** (`annotation_engine.py`): Assigns additional vocabulary IDs via external APIs
   - Uses annotator plugins in `annotators/` implementing `BaseAnnotator`
   - Engine selects annotators based on entity type

2. **Normalization** (`normalizer/normalizer.py`): Converts local IDs to Biolink-standard CURIEs
   - Validates IDs via `validators.py` and `vocab_config.py`

3. **Linking** (`linker.py`): Maps CURIEs to knowledge graph node IDs via Kestrel API

4. **Resolution** (`resolver.py`): Resolves one-to-many KG matches by voting (CURIE support count)

## Key Entry Points
- `Mapper.map_entity_to_kg()`: Single entity mapping
- `Mapper.map_dataset_to_kg()`: Bulk dataset mapping from TSV files

## Project Structure
```
src/biomapper2/
├── mapper.py           # Main Mapper class
├── config.py           # Configuration (API URLs, env vars)
├── utils.py            # Utility functions
└── core/
    ├── annotation_engine.py
    ├── linker.py
    ├── resolver.py
    ├── annotators/     # Annotator plugins
    │   ├── base.py     # BaseAnnotator abstract class
    │   ├── kestrel_text.py
    │   └── metabolomics_workbench.py
    └── normalizer/
        ├── normalizer.py
        ├── validators.py
        ├── vocab_config.py
        └── cleaners.py
```

## Tech Stack
- **Language**: Python 3.10+
- **Package Manager**: uv
- **Build System**: hatchling
- **Core Dependencies**: pandas, numpy, requests, rdkit, python-dotenv, pyyaml

## Configuration
- `KESTREL_API_URL`: Knowledge graph API endpoint
- `KESTREL_API_KEY`: Required environment variable (from `.env`)
- `BIOLINK_VERSION_DEFAULT`: Biolink model version
