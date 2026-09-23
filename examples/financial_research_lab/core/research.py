from dataclasses import dataclass


@dataclass(frozen=True)
class ResearchObservation:
    source: str
    value: float

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("source must not be empty")
