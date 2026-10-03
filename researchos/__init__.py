"""
ResearchOS — Institutional Market Research Platform

A deterministic, explainable, scientific market research platform
that produces institutional-quality research for human traders.

This package implements the ResearchOS constitutional framework
(Articles I-XVII) as a Python library.

Key Principles:
    - Determinism: Every computation is deterministic and reproducible
    - Explainability: Every conclusion has a complete reasoning trace
    - Scientific Rigor: Every hypothesis is falsifiable
    - No Trading: ResearchOS never executes trades or sends orders

Usage:
    from researchos import Research, Observation, Evidence

See: docs/01_VISION.md through docs/17_OBJECT_MODEL.md
"""

__version__ = "1.0.1"
__status__ = "Phase 0 — Constitutional Foundation"

from researchos.core.base_object import BaseObject
from researchos.core.identity import generate_id
from researchos.core.lifecycle import Lifecycle
from researchos.core.timestamp import utc_now
from researchos.objects.confidence import Confidence, ConfidenceReport
from researchos.objects.contradiction import Contradiction, ContradictionReport
from researchos.objects.evidence import Evidence, EvidenceRegistry
from researchos.objects.hypothesis import Hypothesis, HypothesisSet
from researchos.objects.interpretation import Interpretation, Narrative
from researchos.objects.knowledge import Knowledge, Lesson, Pattern
from researchos.objects.observation import MacroState, MarketState, Observation
from researchos.objects.research import Research, ResearchQuestion, ResearchReport
from researchos.objects.scenario import Scenario, ScenarioSet

__all__ = [
    "BaseObject",
    "generate_id",
    "Lifecycle",
    "utc_now",
    "Observation",
    "MarketState",
    "MacroState",
    "Evidence",
    "EvidenceRegistry",
    "Interpretation",
    "Narrative",
    "Hypothesis",
    "HypothesisSet",
    "Scenario",
    "ScenarioSet",
    "Confidence",
    "ConfidenceReport",
    "Contradiction",
    "ContradictionReport",
    "Knowledge",
    "Pattern",
    "Lesson",
    "Research",
    "ResearchReport",
    "ResearchQuestion",
]

# Strict diagnostic trigger; no runtime behavior change.
