from researchos.masterclass import (
    ConditionalOutcome,
    EconomicObservation,
    EvidenceBundle,
    HumanState,
    MarketRelationship,
    MasterclassPipeline,
    TechnicalEvidence,
)


def test_masterclass_is_deterministic_and_hash_linked():
    bundle = EvidenceBundle(
        macro=(
            EconomicObservation(
                name="CPI",
                timestamp="2026-10-08T00:00:00Z",
                actual=3.1,
                expected=3.0,
                previous=3.2,
                source="test",
            ),
        ),
        relationships=(
            MarketRelationship(
                source="DXY",
                target="XAUUSD",
                correlation=-0.7,
                window=60,
                direction="bearish",
            ),
        ),
        technical=(
            TechnicalEvidence(
                name="liquidity_sweep",
                direction="bullish",
                strength=0.8,
                confidence=0.9,
                timestamp="2026-10-08T00:01:00Z",
                tags=("liquidity", "sweep"),
            ),
        ),
        human=HumanState(
            timestamp="2026-10-08T00:01:00Z",
            sleep_quality=0.8,
            fatigue=0.2,
            stress=0.2,
            attention=0.9,
        ),
        psychology=(),
        historical=ConditionalOutcome(
            condition_key=("macro:cpi_surprise_positive", "technical:sweep"),
            bullish_wins=70,
            bearish_wins=30,
        ),
    )
    pipeline = MasterclassPipeline()
    a = pipeline.build(bundle)
    b = pipeline.build(bundle)
    assert a.evidence_hash == b.evidence_hash
    assert a.bullish_probability + a.bearish_probability + a.neutral_probability == 1.0
    assert 0.0 <= a.bullish_probability <= 1.0
    assert a.expected_r is not None


def test_masterclass_emits_canonical_decision_evidence():
    bundle = EvidenceBundle(
        technical=(
            TechnicalEvidence(
                name="bos",
                direction="bullish",
                strength=1.0,
                confidence=1.0,
                timestamp="2026-10-08T00:00:00Z",
            ),
        )
    )
    pipeline = MasterclassPipeline()
    evidence = pipeline.to_decision_evidence(pipeline.build(bundle))
    assert len(evidence) == 1
    assert evidence[0].source_id.startswith("masterclass:")
