---
title: "Cross-repo dynamic API integration: entity types and vocabulary presets"
date: 2026-05-27
category: best-practices
module: biomapper2.api
problem_type: best_practice
component: tooling
severity: medium
applies_when:
  - Changing an API response shape consumed by external client libraries
  - Deploying multi-service changes to a shared server
  - Deriving UI defaults from knowledge graph metadata
  - Debugging failures in multi-layer proxy chains
tags:
  - cross-repo-coordination
  - api-contract
  - kestrel
  - pydantic-serialization
  - cache-invalidation
  - proxy-routing
  - deployment
---

# Cross-repo dynamic API integration: entity types and vocabulary presets

## Context

Dynamic entity types and vocabulary prefix presets were added to biomapper2 by fetching categories from the Kestrel knowledge graph API and deriving per-category prefix rankings from text-search sampling. This required coordinated changes across three repos (biomapper2 backend, biomapper Python client library, biomapper-ui frontend) and exposed several integration patterns that are easy to get wrong.

The request chain traverses four layers: React frontend -> Node/Express proxy -> Python intermediary (using the `biomapper` client library) -> biomapper2 FastAPI backend. Each layer has its own caching, serialization, auth, and dependency management.

## Guidance

### 1. Trace the full consumer chain before changing API shapes

When changing a response shape, identify every downstream consumer — not just the immediate caller. In this case:

```
biomapper2 API (response shape change)
  -> biomapper client library (PyPI package, pinned in requirements.txt)
    -> biomapper-ui Python intermediary (calls client, serializes via model_dump)
      -> biomapper-ui Node proxy (forwards JSON as-is)
        -> React frontend (consumes JSON)
```

The frontend already expected the new shape (its OpenAPI spec was written ahead of the backend), but the Python client library (v1.1.0) crashed on it, causing 502s through the entire chain.

### 2. Pin dependencies explicitly in deploy pipelines

The biomapper-ui `requirements.txt` pinned `biomapper==1.1.0`. Every deploy reinstalled this version, silently overwriting manual `pip install --upgrade` fixes on the server. The fix: update `requirements.txt` to `biomapper>=1.2.1` so deploys pick up the correct version.

### 3. Pydantic alias configuration for cross-language serialization

Three different alias mechanisms exist in Pydantic v2, and choosing the wrong one causes subtle failures:

| Mechanism | Affects `model_validate()` | Affects `model_dump()` | Affects constructor |
|-----------|---------------------------|------------------------|---------------------|
| `alias` | Yes | Yes (with `by_alias=True`) | Yes (requires `populate_by_name=True` for Python name) |
| `validation_alias` | Yes | No | No |
| `serialization_alias` | No | Yes (with `by_alias=True`) | No |

For a Python backend emitting camelCase JSON to a JavaScript frontend, use `serialization_alias` on the server model and `alias` + `populate_by_name=True` on the client model. Always call `model_dump(by_alias=True)` at the serialization boundary.

### 4. Multi-layer caching requires coordinated invalidation

Three caching layers existed:
- **requests_cache** (SQLite, 1hr TTL) — cached raw Kestrel HTTP responses
- **Disk cache** (JSON file) — cached derived presets across restarts
- **In-memory** (app.state) — cached presets for the running process

A service restart only clears in-memory state. If the HTTP cache serves stale responses within its TTL, the new code derives the same old presets. Fix: delete `cache/kestrel_http.sqlite` and `cache/entity_type_presets.json` before restarting when response shapes change.

### 5. Kill orphaned processes before deploying to shared ports

Processes started via tmux survive systemd service restarts. An orphaned process from April bound to `127.0.0.1:8003` responded to health checks before the new systemd service could bind, making the deploy appear successful while serving old code. (session history)

Check before deploying: `ps aux | grep 'port 8003' | grep -v grep`

### 6. Knowledge graph prefix frequency is dominated by cross-reference vocabularies

UMLS, NCIT, CHV, EFO, and MESH appear on 5-9 of 9 sampled categories because they are general-purpose cross-reference namespaces in the KG. Domain-specific prefixes (CHEBI, HMDB, ENSEMBL) rank lower despite being what users actually need.

Rather than maintaining exclusion lists or tuning thresholds, the solution was to return the top 30 prefixes by frequency (unfiltered), present them unchecked and alphabetized in the UI, and let users choose. This avoids encoding domain assumptions into backend logic.

## Why This Matters

Multi-repo API changes amplify failure modes. A single response shape change cascaded through a client library, a Python intermediary, a Node proxy, and a React frontend — each with independent caching, serialization, and dependency management. Without tracing the full chain, deployments fail in ways that are hard to diagnose: stale caches serving old shapes, pinned versions overwriting manual fixes, orphaned processes ignoring new code.

The prefix ranking lesson applies broadly: when deriving UI defaults from knowledge graph metadata, the most frequent entities in the graph are often administrative cross-references, not the domain-specific vocabularies users care about.

## When to Apply

- Any API response shape change in biomapper2 consumed by the biomapper client library
- Deploying to the Lightsail instance after changing API contracts
- Adding new Pydantic models that cross a Python-to-JavaScript boundary
- Designing vocabulary or ontology selection features from KG metadata
- Debugging "works locally but not in production" across multi-service chains

## Examples

**Safe deployment checklist for Lightsail:**
1. Kill orphaned processes: `ps aux | grep 'port 8003' | grep -v grep`
2. Clear caches if response shapes changed: `rm -f cache/kestrel_http.sqlite cache/entity_type_presets.json`
3. Restart the systemd service
4. Verify correct code: `curl http://localhost:8003/api/v1/health`
5. Test end-to-end from the UI, not just the backend

**Pydantic serialization alias (server-side):**
```python
# Server: emit camelCase JSON
class EntityType(BaseModel):
    default_prefixes: list[str] | None = Field(
        default=None, serialization_alias="defaultPrefixes"
    )
# Route: response_model_by_alias=True
```

**Pydantic alias (client-side):**
```python
# Client: accept camelCase from wire, use snake_case in Python
class EntityTypeInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    default_prefixes: list[str] = Field(default_factory=list, alias="defaultPrefixes")
# Intermediary: item.model_dump(by_alias=True) to re-emit camelCase
```

## Related

- `docs/solutions/build-errors/equivalent-ids-prefix-mismatch-and-ci-type-error-2026-04-29.md` — established the "don't hardcode vocabulary lists that mirror external data" principle that this feature implements
- Phenome-Health/biomapper2#52 — Start supporting microbiome datasets (addressed by this work)
- Phenome-Health/biomapper2#51 — Auto-determine entity types for items in a dataset (future work building on this infrastructure)
- Phenome-Health/biomapper2#13 — Standardize input entity_type on Biolink categories (effectively implemented by dynamic categories)
