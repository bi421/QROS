from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Vector2D:
    x: float
    y: float
    def magnitude(self) -> float: return (self.x*self.x+self.y*self.y)**0.5
    def dot(self, other: "Vector2D") -> float: return self.x*other.x+self.y*other.y

@dataclass(frozen=True)
class GeometryMeasurement:
    slope: float
    angle_radians: float
    angle_degrees: float
    distance: float
    vector: Vector2D
    curvature: float
    trend_r2: float
    support_level: float|None
    resistance_level: float|None

@dataclass(frozen=True)
class StatisticalMeasurement:
    count:int; mean:float; variance:float; standard_deviation:float
    minimum:float; maximum:float; z_score_last:float
    correlation:float|None; regression_slope:float|None
    regression_intercept:float|None; regression_r2:float|None

@dataclass(frozen=True)
class BayesianMeasurement:
    prior_alpha:float; prior_beta:float; successes:int; failures:int
    posterior_alpha:float; posterior_beta:float; posterior_mean:float

@dataclass(frozen=True)
class MonteCarloMeasurement:
    simulations:int; seed:int; mean_terminal:float
    standard_deviation_terminal:float; percentile_05:float
    percentile_50:float; percentile_95:float

@dataclass(frozen=True)
class QuantMathResult:
    calculation_version:str
    geometry:GeometryMeasurement
    statistics:StatisticalMeasurement
    bayesian:BayesianMeasurement|None
    monte_carlo:MonteCarloMeasurement|None
    result_hash:str
    def to_dict(self)->dict[str,Any]:
        return {"calculation_version":self.calculation_version,"geometry":self.geometry.__dict__,
                "statistics":self.statistics.__dict__,
                "bayesian":None if self.bayesian is None else self.bayesian.__dict__,
                "monte_carlo":None if self.monte_carlo is None else self.monte_carlo.__dict__,
                "result_hash":self.result_hash}
