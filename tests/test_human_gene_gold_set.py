"""Live merge-gate validation: human genes/proteins must resolve to the human node, not an ortholog.

Marked `integration` (hits the live Kestrel API). Runs the full pipeline via Mapper.map_entity_to_kg
with the default-on prefer_human behavior, asserts each positive gold entity resolves to the expected
human NCBIGene carrying an HGNC marker, and persists a timestamped report (per the experiment-artifact
SOP). GH1 is a negative control: its human node is absent from Kestrel hybrid-search even at limit=50
(verified 2026-06-15), so it is expected to fall back gracefully and is counted in the fallback fraction.
"""

import json
from datetime import datetime, timezone

import pytest

from biomapper2.config import PROJECT_ROOT

# Positive cases: must resolve to the expected human NCBIGene (verified at rank ~#4 in the Unit 1 spike).
# Includes a paralog pair (TNFRSF1A/TNFRSF1B) to exercise the R7 wrong-paralog guard against live data.
POSITIVE_GOLD = {
    "TNFRSF1A": "NCBIGene:7132",
    "TNFRSF1B": "NCBIGene:7133",
    "LDLR": "NCBIGene:3949",
}
# Negative control: human node absent from Kestrel candidates -> expected to fall back (Kestrel recall gap).
NEGATIVE_CONTROL = {"GH1": "NCBIGene:2688"}


def _has_hgnc(result: dict) -> bool:
    """True if the resolved node carries an HGNC marker in its equivalent ids."""
    return "HGNC" in json.dumps(result.get("kg_equivalent_ids", {}))


def _map_gene(shared_mapper, name: str) -> dict:
    return shared_mapper.map_entity_to_kg(
        item={"name": name},
        name_field="name",
        provided_id_fields=[],
        entity_type="gene",
    )


@pytest.fixture(scope="module")
def gold_set_run(shared_mapper):
    """Run the full gold set live once, persist a timestamped report, and return the per-entity results."""
    rows = []
    for name, expected in {**POSITIVE_GOLD, **NEGATIVE_CONTROL}.items():
        result = _map_gene(shared_mapper, name)
        chosen = result.get("chosen_kg_id")
        rows.append(
            {
                "name": name,
                "expected_human": expected,
                "chosen_kg_id": chosen,
                "is_expected_human": chosen == expected,
                "has_hgnc": _has_hgnc(result),
                "is_positive": name in POSITIVE_GOLD,
            }
        )

    positives = [r for r in rows if r["is_positive"]]
    fell_back = [r for r in rows if not r["is_expected_human"]]
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "prefer_human": True,
        "n_total": len(rows),
        "n_positive": len(positives),
        "n_positive_resolved": sum(r["is_expected_human"] for r in positives),
        "fallback_fraction": round(len(fell_back) / len(rows), 3),
        "rows": rows,
    }

    out_dir = PROJECT_ROOT / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"hgnc_gold_set_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\n[gold-set] report saved to {out_path} (fallback_fraction={report['fallback_fraction']})")

    return report


@pytest.mark.integration
class TestHumanGeneGoldSet:
    @pytest.mark.parametrize("name", sorted(POSITIVE_GOLD))
    def test_positive_resolves_to_human_node(self, gold_set_run, name):
        """Each positive gold entity resolves to the expected human NCBIGene AND carries an HGNC marker."""
        row = next(r for r in gold_set_run["rows"] if r["name"] == name)
        assert row["chosen_kg_id"] == POSITIVE_GOLD[name], f"{name} -> {row['chosen_kg_id']} (expected human)"
        assert row["has_hgnc"], f"{name} resolved node lacks an HGNC marker"

    def test_gh1_negative_control_falls_back_gracefully(self, gold_set_run):
        """GH1's human node is unreachable in Kestrel -> pipeline must return a node, not crash."""
        row = next(r for r in gold_set_run["rows"] if r["name"] == "GH1")
        assert row["chosen_kg_id"] is not None  # graceful fallback (honest miss), no exception
        assert not row["is_expected_human"]  # documents the known Kestrel-recall residual

    def test_fallback_fraction_reported(self, gold_set_run):
        """The run quantifies and persists the fallback fraction (R8 observability)."""
        assert 0.0 <= gold_set_run["fallback_fraction"] <= 1.0
        # All positives should resolve; only the negative control is expected to fall back.
        assert gold_set_run["n_positive_resolved"] == gold_set_run["n_positive"]
