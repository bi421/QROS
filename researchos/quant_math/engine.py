from __future__ import annotations
import json
from collections.abc import Sequence
from hashlib import sha256
from researchos.quant_math.bayesian import beta_bernoulli
from researchos.quant_math.contracts import QuantMathResult
from researchos.quant_math.geometry import measure_market_geometry
from researchos.quant_math.monte_carlo import simulate_terminal_distribution
from researchos.quant_math.statistics import describe
QUANT_MATH_VERSION="QUANT_MATH_V1"
class QuantMathEngine:
    calculation_version=QUANT_MATH_VERSION
    def evaluate(self,prices:Sequence[float],successes:int|None=None,failures:int|None=None,monte_carlo_simulations:int|None=None,seed:int=42)->QuantMathResult:
        geometry=measure_market_geometry(prices); statistics=describe(prices); bayesian=None; monte_carlo=None
        if successes is not None or failures is not None:
            if successes is None or failures is None: raise ValueError("successes and failures must be supplied together")
            bayesian=beta_bernoulli(successes,failures)
        if monte_carlo_simulations is not None: monte_carlo=simulate_terminal_distribution(prices,monte_carlo_simulations,seed)
        payload={"calculation_version":self.calculation_version,"geometry":geometry.__dict__,"statistics":statistics.__dict__,"bayesian":None if bayesian is None else bayesian.__dict__,"monte_carlo":None if monte_carlo is None else monte_carlo.__dict__}
        digest=sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        return QuantMathResult(self.calculation_version,geometry,statistics,bayesian,monte_carlo,digest)
