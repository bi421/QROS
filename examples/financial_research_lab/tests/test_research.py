from financial_research_lab.core.research import ResearchObservation


def test_observation() -> None:
    item = ResearchObservation("test", 100.0)
    assert item.source == "test"
    assert item.value == 100.0


def test_observation_is_immutable() -> None:
    item = ResearchObservation("test", 100.0)
    try:
        item.value = 200.0
    except AttributeError:
        pass
    else:
        raise AssertionError("Observation must be immutable")
