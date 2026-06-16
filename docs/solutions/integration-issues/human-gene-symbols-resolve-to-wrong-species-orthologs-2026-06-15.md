---
title: "Human gene/protein symbols resolve to wrong-species orthologs (Kestrel hybrid-search limit=1)"
date: 2026-06-15
category: integration-issues
module: kestrel_hybrid
problem_type: integration_issue
component: service_object
symptoms:
  - "Human gene symbol resolves to a non-human ortholog NCBIGene ID at confidence_tier=high (TNFRSF1A -> NCBIGene:397020 instead of NCBIGene:7132)"
  - "~42 of 50 human frailty proteins map to wrong-species ortholog nodes with <50 KG edges"
  - "Downstream consumer (kraken) sees a false cold-start: human genes mis-classified as under-characterized"
  - "No error raised -- the wrong node is returned silently with a high score (e.g. 4.876)"
root_cause: wrong_api
resolution_type: code_fix
severity: high
related_components:
  - annotation_engine
  - linker
tags:
  - kestrel
  - hybrid-search
  - ortholog
  - species-disambiguation
  - hgnc
  - gene-mapping
  - prefer-human
---

# Human gene/protein symbols resolve to wrong-species orthologs (Kestrel hybrid-search limit=1)

## Problem

For human gene/protein symbols, biomapper2 resolved a bare symbol to a non-human **ortholog** at
`confidence_tier="high"`, because the underlying Kestrel hybrid-search annotator requested only the
top-1 candidate (`limit=1`) and Kestrel's #1 hit is frequently the wrong-species ortholog. The human
node exists in Kestrel's candidate list (typically rank ~#4) but was discarded before selection.

## Symptoms

- `TNFRSF1A` (`biolink:Gene`) resolved to `NCBIGene:397020` (pig/rat ortholog, score 4.876) instead of
  human `NCBIGene:7132` (3777 edges). `GH1` → bovine ortholog; `LDLR` similarly non-human.
- All mis-resolutions came back at `confidence_tier="high"` — nothing flagged them as suspect.
- Downstream consumer (kraken) saw a "false cold-start": ~42/50 frailty proteins resolved to non-human
  `NCBIGene` orthologs with <50 KG edges and were mis-classified as under-characterized.
- The biomapper2 score was **byte-identical** to Kestrel hybrid-search's own ortholog score —
  confirming biomapper2 *is* Kestrel hybrid-search underneath, with no re-ranking of its own.

## What Didn't Work

- **Kestrel `prefix_filter` / `category_filter` for species** — fails: Kestrel keys *all* gene nodes on
  `NCBIGene` regardless of species (human `NCBIGene:7132` and pig `NCBIGene:397020` share the prefix),
  so a request-side prefix filter cannot separate species. (Kestrel's MCP layer rejects `prefix_filter`
  outright; the REST endpoint accepts it but it still can't filter by species.)
- **`annotation_mode` variations** — `'all'` still returns the ortholog as top-1; `'best'` /
  `'comprehensive'` are invalid and return HTTP 422.
- **A client-side workaround in the downstream consumer (kraken)** — a biomapper pre-resolver + HGNC
  confirmation gate — delivered **zero lift**, because biomapper2 *is* Kestrel underneath. The fix had
  to be at the source (biomapper2) where it benefits every consumer, not bolted onto one consumer.

## Solution

The insight: **HGNC assigns IDs only to human genes** (there is no bovine HGNC id), and the Kestrel
hybrid-search response rows **already carry a `prefixes` list** — the human `NCBIGene:7132` row's
prefixes include `"HGNC"`; ortholog rows (`["NCBIGene","RGD","UniProtKB","ENSEMBL"]`) do not. So the
human candidate is identifiable from the response alone — no extra Kestrel call.

**1. Raise the candidate window, gated to where it applies** (`src/biomapper2/config.py`):

```python
HYBRID_SEARCH_LIMIT = 20            # human node found at rank ~#4 live; 20 gives margin
HUMAN_MARKER_PREFIXES = {"HGNC"}    # human-exclusive marker
```

The raised limit is applied **only for gene/protein** so metabolite/other bulk payloads aren't inflated
~20× (`src/biomapper2/core/annotators/kestrel_hybrid.py`):

```python
limit = HYBRID_SEARCH_LIMIT if prefer_human else 1
```

**2. Two-tier candidate selection** (`_select_result` in `kestrel_hybrid.py`):

```python
@staticmethod
def _select_result(term_results, search_term, prefer_human):
    if not term_results:
        return None
    if not prefer_human:
        return term_results[0]                                       # legacy top-1

    human = [r for r in term_results if HUMAN_MARKER_PREFIXES & set(r.get("prefixes") or [])]
    if not human:
        return term_results[0]                                       # honest fallback -- never fabricate

    exact = [r for r in human if KestrelHybridSearchAnnotator._symbol_matches(r, search_term)]
    pool = exact if exact else human
    return max(pool, key=lambda r: r.get("score", 0))
```

The HGNC filter must come **before** the symbol match: orthologs share the human row's `name` (same
symbol, different species), so HGNC separates species first, then the symbol match (`_symbol_matches`:
case-insensitive equality on `name`, or membership in `synonyms`) picks the right gene. The symbol-match
step is critical because a human **paralog** (e.g. `TNFRSF1B` → `NCBIGene:7133`) *also* carries HGNC —
matching the queried symbol avoids trading a wrong-species bug for a wrong-gene bug. Defensive reads
(`r.get("prefixes") or []`, `r.get("score", 0)`) tolerate malformed/null rows.

**3. Gate behind a default-on `prefer_human` option**, threaded `MappingOptions` → routes → `Mapper` →
`AnnotationEngine` → annotator. The engine resolves applicability and passes an already-gated effective
flag (`src/biomapper2/core/annotation_engine.py`):

```python
effective_prefer_human = prefer_human and self._is_human_applicable_category(category)

@cached_property
def _human_applicable_categories(self) -> set[str]:
    return self.biolink_client.get_descendants("biolink:Gene") | \
           self.biolink_client.get_descendants("biolink:Protein")
```

`prefer_human=False` restores legacy top-1; metabolites are unchanged. `MappingOptions` uses Pydantic v2
`extra="ignore"` so an older server doesn't 422 on the new field (backward-compat).

## Why This Works

The root cause was twofold: `limit=1` discarded the human candidate before any selection could happen,
and species discrimination was attempted on the **request** side, where it is impossible (Kestrel keys
every species on `NCBIGene`). The fix moves discrimination to the **response** side, where the human
node is unambiguously marked by an `HGNC` prefix — a human-only identifier already present in the rows
Kestrel returns. Raising the limit ensures the human node is actually in hand; the post-filter then
separates species where `prefix_filter` structurally cannot. No additional API call is needed.

## Prevention

- **Symbol-match within the HGNC pool** to avoid trading wrong-species for wrong-paralog (paralogs also
  carry HGNC).
- **Honest fallback**: when no HGNC row exists, return the top candidate rather than fabricating a human
  match — a graceful, observable miss.
- **Make the fallback fraction observable** (reported in the gold-set validation run) so consumers can
  detect recall gaps instead of silently trusting `confidence_tier="high"`.
- **`pytest.mark.xfail(strict=False)` for unfixable upstream recall gaps**: `GH1`'s human node
  `NCBIGene:2688` is absent from Kestrel hybrid-search even at `limit=50` (Gene and Protein categories) —
  a Kestrel *recall* gap a re-rank cannot fix. The xfail documents the gap and auto-passes (xpass) when
  Kestrel later indexes the node; pair it with an unconditional graceful-fallback assertion.
- **Test with mocked hybrid rows that include `prefixes`** (and `name`/`synonyms`) so `_select_result` /
  `_symbol_matches` are exercised offline. The live integration/gold-set test cannot run in a sandbox
  because building `Mapper()`/`BiolinkClient` hangs on bmt (Biolink Model Toolkit) init, which is
  network-blocked there — so the fix was verified live against the deployed dev API instead. *(auto
  memory [claude])*
- **Fix at the source, not the consumer**: when a downstream workaround delivers zero lift, suspect the
  downstream service *is* the thing it's trying to correct; fixing it once at the source benefits every
  consumer.

## Verification

Live against the deployed dev API (`dev-biomapper.expertintheloop.io`):

| Query | `prefer_human` | Resolved → | HGNC |
|-------|----------------|-----------|------|
| `TNFRSF1A` | `true` (default) | `NCBIGene:7132` (human) | ✓ |
| `TNFRSF1A` | `false` | `NCBIGene:397020` (legacy ortholog) | ✗ |
| `TNFRSF1B` | `true` | `NCBIGene:7133` (correct paralog) | ✓ |
| `LDLR` | `true` | `NCBIGene:3949` | ✓ |
| `glucose` (metabolite) | `true` | `CHEBI:4167` (unchanged) | ✗ |

## Related Issues

- `docs/solutions/build-errors/equivalent-ids-prefix-mismatch-and-ci-type-error-2026-04-29.md` — same
  Kestrel `prefixes` subsystem (LM/RM prefix-string mismatch + CI pyright). **Caveat:** its assumption
  that "prefix filtering cleanly separates vocabularies per entity type" does **not** extend to species
  — Kestrel keys all species on `NCBIGene`, which is exactly what this bug exploits via the HGNC marker.
- `docs/solutions/best-practices/cross-repo-dynamic-api-integration-2026-05-27.md` — see-also for the
  `api/models/requests.py` request-contract surface (where the `prefer_human` option was added) and the
  Kestrel HTTP cache-invalidation gotcha.
- Shipped via PRs: `trentleslie/biomapper2#5` (fork, Greptile) → `Phenome-Health/biomapper2#69` (dev) →
  `#70` (dev → main). Cross-repo follow-up: expose the per-request `prefer_human` opt-out in the
  `biomapper` Python client.
