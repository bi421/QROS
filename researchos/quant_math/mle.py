from __future__ import annotations
import math
from collections.abc import Sequence

MLE_VERSION="MLE_V1"

def normal_mle(values:Sequence[float])->tuple[float,float]:
    v=[float(x) for x in values]
    if not v: raise ValueError("MLE requires observations")
    if any(not math.isfinite(x) for x in v): raise ValueError("MLE observations must be finite")
    mu=sum(v)/len(v)
    sigma2=sum((x-mu)**2 for x in v)/len(v)
    return mu,sigma2

def bernoulli_mle(successes:int,trials:int)->float:
    if trials<=0 or successes<0 or successes>trials: raise ValueError("invalid Bernoulli counts")
    return successes/trials
