"""Tests for threading the `prefer_human` flag from the API options model down to the annotator.

These cover the engine's category-applicability gate and the request-model contract without hitting
the live Kestrel API or the (slow) Biolink Model Toolkit (the annotator's selection logic is covered
in test_kestrel_hybrid_selection.py; the live gold-set is covered by the integration test).

The Biolink client is stubbed so the gate logic is exercised hermetically -- no bmt init, no network.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from biomapper2.api.models.requests import MappingOptions
from biomapper2.core.annotation_engine import AnnotationEngine

HYBRID_SLUG = "kestrel-hybrid-search"


def _fake_biolink():
    """Stub BiolinkClient.get_descendants: reflexive, with Gene/Protein as their own (only) descendants."""
    fake = MagicMock()
    fake.get_descendants.side_effect = lambda c: {c}
    return fake


@pytest.fixture
def engine():
    """A real AnnotationEngine with a stubbed Biolink client (avoids the slow bmt initialization)."""
    return AnnotationEngine(biolink_client=_fake_biolink())


def _spy_single(engine: AnnotationEngine, monkeypatch) -> MagicMock:
    """Spy the hybrid annotator's get_annotations (auto-restored after the test by monkeypatch)."""
    spy = MagicMock(return_value={HYBRID_SLUG: {}})
    monkeypatch.setattr(engine.annotator_registry[HYBRID_SLUG], "get_annotations", spy)
    return spy


def _spy_bulk(engine: AnnotationEngine, monkeypatch) -> MagicMock:
    """Spy the hybrid annotator's get_annotations_bulk with an index-preserving return."""

    def _return(entities, *_args, **_kwargs):
        return pd.Series([{HYBRID_SLUG: {}} for _ in range(len(entities))], index=entities.index)

    spy = MagicMock(side_effect=_return)
    monkeypatch.setattr(engine.annotator_registry[HYBRID_SLUG], "get_annotations_bulk", spy)
    return spy


class TestMappingOptionsContract:
    def test_prefer_human_defaults_true(self):
        """Default-on (R4): an options object created without the field has prefer_human True."""
        assert MappingOptions().prefer_human is True

    def test_prefer_human_can_be_disabled(self):
        assert MappingOptions(prefer_human=False).prefer_human is False

    def test_unknown_extra_field_is_ignored(self):
        """Backward-compat (R5): an unknown option from a newer client does not raise."""
        opts = MappingOptions.model_validate({"prefer_human": True, "some_future_option": 123})
        assert opts.prefer_human is True
        assert not hasattr(opts, "some_future_option")


class TestEngineApplicabilityGate:
    def test_gene_category_receives_effective_true(self, engine, monkeypatch):
        """Happy path: gene category + prefer_human=True -> annotator receives effective True."""
        spy = _spy_single(engine, monkeypatch)
        engine.annotate(
            item=pd.Series({"name": "TNFRSF1A"}),
            name_field="name",
            provided_id_fields=[],
            category="biolink:Gene",
            prefixes=[],
            mode="all",
            annotators=[HYBRID_SLUG],
            prefer_human=True,
        )
        assert spy.call_args.kwargs["prefer_human"] is True

    def test_metabolite_category_receives_effective_false(self, engine, monkeypatch):
        """Edge: metabolite category gates the flag off even when prefer_human=True is requested."""
        spy = _spy_single(engine, monkeypatch)
        engine.annotate(
            item=pd.Series({"name": "glucose"}),
            name_field="name",
            provided_id_fields=[],
            category="biolink:SmallMolecule",
            prefixes=[],
            mode="all",
            annotators=[HYBRID_SLUG],
            prefer_human=True,
        )
        assert spy.call_args.kwargs["prefer_human"] is False

    def test_prefer_human_false_overrides_applicable_category(self, engine, monkeypatch):
        """Edge: explicit opt-out yields effective False even for an applicable gene category."""
        spy = _spy_single(engine, monkeypatch)
        engine.annotate(
            item=pd.Series({"name": "TNFRSF1A"}),
            name_field="name",
            provided_id_fields=[],
            category="biolink:Gene",
            prefixes=[],
            mode="all",
            annotators=[HYBRID_SLUG],
            prefer_human=False,
        )
        assert spy.call_args.kwargs["prefer_human"] is False

    def test_bulk_path_forwards_effective_flag(self, engine, monkeypatch):
        """Integration (bulk gate): the DataFrame path forwards the effective flag to get_annotations_bulk."""
        spy = _spy_bulk(engine, monkeypatch)
        df = pd.DataFrame({"name": ["TNFRSF1A", "LDLR"]})
        engine.annotate(
            item=df,
            name_field="name",
            provided_id_fields=[],
            category="biolink:Gene",
            prefixes=[],
            mode="all",
            annotators=[HYBRID_SLUG],
            prefer_human=True,
        )
        assert spy.call_args.kwargs["prefer_human"] is True
