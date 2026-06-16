---
title: Equivalent IDs prefix mismatch and CI pyright type error
date: 2026-04-29
last_updated: 2026-06-15
category: build-errors
module: biomapper2.core.linker
problem_type: build_error
component: tooling
symptoms:
  - "Hardcoded LIPIDMAPS prefix never matched Kestrel KG data (actual prefix: LM)"
  - "Hardcoded REFMET prefix was a dead entry (Kestrel uses RM, already in the list)"
  - "CI pyright failure: No overloads for __setitem__ match the provided arguments (reportCallIssue)"
  - "Dev API returning stale results after code update due to orphaned uvicorn process"
root_cause: config_error
resolution_type: code_fix
severity: medium
related_components:
  - testing_framework
  - development_workflow
tags:
  - equivalent-ids
  - kestrel-api
  - pyright
  - ci-failure
  - prefix-filtering
  - dev-api-deployment
  - nginx
---

# Equivalent IDs prefix mismatch and CI pyright type error

## Problem

The `feat/equivalent-ids` branch introduced a hardcoded `DEFAULT_EQUIVALENT_ID_PREFIXES` list in `Linker.get_equivalent_ids()` to filter equivalent IDs from Kestrel KG nodes. Two prefixes were wrong (`LIPIDMAPS` should have been `LM`, `REFMET` was redundant with `RM`), and the hardcoded approach itself was flawed — any new vocabularies added to the KG would be silently excluded. After fixing the prefixes and removing the hardcoded filter, CI failed with a pyright type error on DataFrame column assignment.

## Symptoms

- **Silent data loss**: LIPID MAPS IDs (e.g., `LM:ST01010001` for cholesterol) were never returned because the filter checked for `LIPIDMAPS` but Kestrel uses `LM` as the CURIE prefix
- **Dead filter entry**: `REFMET` never matched anything — Kestrel uses `RM`, which was already in the list
- **CI failure**: After pushing the fix, GitHub Actions pyright check failed:
  ```
  src/biomapper2/mapper.py:248:13 - error: No overloads for "__setitem__" match
  the provided arguments (reportCallIssue)
  Argument of type "list[dict[Any, Any]]" cannot be assigned to parameter "value"
  ```
- **Stale dev API responses**: After deploying updated code to the dev server, responses still showed filtered results because an orphaned uvicorn process from a previous deployment was still bound to port 8003

## What Didn't Work

- **Hardcoded prefix allowlist**: The original approach maintained a 17-prefix allowlist (`DEFAULT_EQUIVALENT_ID_PREFIXES`). This required manual maintenance, was already wrong on day one (2 of 17 prefixes were incorrect), and would silently drop any new vocabularies added to the KG. Querying Kestrel revealed 41 unique prefixes across a sample of entities — 24 were being silently excluded.

- **tmux kill-session for server restart**: Killing the tmux session did not kill an orphaned uvicorn process from a prior `nohup` deployment. The old process kept port 8003 bound, serving stale code. Had to identify and kill the specific PIDs (`ps aux | grep 'port 8003'`) before starting a fresh tmux session.

- **Direct list assignment to DataFrame column**: `df["kg_equivalent_ids"] = [{} for _ in range(len(df))]` — pyright correctly flags `list[dict[Any, Any]]` as not assignable to a DataFrame column. This passed local pyright (likely due to version differences) but failed in CI.

## Solution

### 1. Remove the hardcoded prefix filter

KG nodes naturally carry only entity-type-relevant vocabularies — a gene node returns HGNC/ENSEMBL/NCBIGene, a metabolite returns HMDB/LM/CHEBI. No hardcoded filter needed.

> **Caveat (added 2026-06-15):** "entity-type-relevant" is about *which vocabularies* a node carries —
> it does **not** mean prefixes can disambiguate **species**. Kestrel keys all gene nodes on `NCBIGene`
> regardless of species, so a request-side `prefix_filter` cannot separate human from ortholog. The
> human-only signal (`HGNC` in a node's/row's prefixes) must be applied as a *response-side* post-filter.
> See `docs/solutions/integration-issues/human-gene-symbols-resolve-to-wrong-species-orthologs-2026-06-15.md`.

**Before:**
```python
DEFAULT_EQUIVALENT_ID_PREFIXES: list[str] = [
    "CHEBI", "CHEMBL.COMPOUND", "DRUGBANK", "ENSEMBL",
    "GTOPDB", "HGNC", "HMDB", "INCHIKEY",
    "KEGG.COMPOUND", "KEGG.DRUG", "LIPIDMAPS",  # wrong prefix
    "MESH", "NCIT", "PUBCHEM.COMPOUND",
    "REFMET",  # dead entry, RM already listed
    "RM", "UNII", "UniProtKB",
]

# In get_equivalent_ids():
if prefixes is None:
    prefixes = Linker.DEFAULT_EQUIVALENT_ID_PREFIXES
```

**After:**
```python
# No hardcoded list. All prefixes returned by default.
# In get_equivalent_ids():

# By default all prefixes are returned — KG nodes naturally carry only
# entity-type-relevant vocabularies (e.g. genes get HGNC/ENSEMBL,
# metabolites get LM/HMDB). The prefixes param is an opt-in hook for
# callers that need to narrow further (e.g. an API query param).
if prefixes and prefix not in prefixes:
    continue
```

The `prefixes` parameter is retained for opt-in filtering — callers can pass `prefixes=["HMDB", "CHEBI"]` to narrow results. When `prefixes` is `None` (default), `if prefixes` is falsy so no filtering occurs.

### 2. Fix the pyright type error

**Before (fails CI pyright):**
```python
df["kg_equivalent_ids"] = [{} for _ in range(len(df))]
```

**After:**
```python
df["kg_equivalent_ids"] = pd.Series([{} for _ in range(len(df))], index=df.index)
```

Wrapping in `pd.Series` satisfies pyright's type checker for DataFrame column assignment.

### 3. Dev API deployment: kill orphaned processes

When restarting the dev API, check for orphaned processes before starting a new tmux session:

```bash
# Kill ALL processes on the dev port, not just the tmux session
ps aux | grep 'port 8003' | grep -v grep
kill <pids>
# Then start fresh
tmux new-session -d -s biomapper2-dev '...'
```

## Why This Works

- **No hardcoded filter**: The KG itself determines which vocabularies are relevant per entity type. Cholesterol returns 28 prefixes (including LM, SMILES, RXCUI), TP53 returns 3 (ENSEMBL, NCBIGene, UniProtKB), insulin returns 27. New vocabularies added to the KG are automatically included without code changes.

- **pd.Series wrapper**: pyright's pandas stubs type `DataFrame.__setitem__` to accept `Scalar | ArrayLike | Series` but not raw `list[dict]`. Wrapping in `pd.Series` matches the expected type signature. This is a type-level fix only — runtime behavior is identical.

- **Process-level restart**: tmux sessions don't guarantee child process cleanup, especially when prior deployments used `nohup`. Explicit PID management ensures the new process gets a clean port.

## Prevention

- **Don't hardcode vocabulary lists that mirror external data sources.** If the source of truth is an API (Kestrel), let the API determine the available data. Hardcoded lists drift on day one and require maintenance forever.

- **Run the full CI check script locally before pushing:** `./scripts/check.sh` runs ruff, black, pyright, and pytest. The pyright version in CI may be stricter — when assigning complex types to DataFrame columns, prefer explicit `pd.Series()` wrapping.

- **Dev API restart checklist:**
  1. `ps aux | grep 'port 8003'` — identify all processes
  2. Kill all of them, not just the tmux session
  3. Start fresh tmux session
  4. Verify with `curl` that the response reflects the new code

## Related Issues

- PR #67: Return equivalent IDs from KG nodes (Phenome-Health/biomapper2)
- Issue #62: Original feature request for equivalent_ids enrichment
