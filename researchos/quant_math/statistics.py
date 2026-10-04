from __future__ import annotations
import math
from collections.abc import Sequence
from researchos.quant_math.contracts import StatisticalMeasurement
STATISTICS_VERSION="STATISTICS_V1"

def _v(values:Sequence[float])->list[float]:
    r=[float(x) for x in values]
    if not r or any(not math.isfinite(x) for x in r):
        raise ValueError("values must contain finite observations")
    return r
def mean(values:Sequence[float])->float:
    r=_v(values)
    return sum(r)/len(r)
def variance(values:Sequence[float],sample:bool=False)->float:
    r=_v(values)
    if sample and len(r)<2:
        raise ValueError("sample variance requires at least two observations")
    m=sum(r)/len(r)
    return sum((x-m)**2 for x in r)/(len(r)-1 if sample else len(r))
def standard_deviation(values:Sequence[float],sample:bool=False)->float:
    return math.sqrt(variance(values,sample))
def pearson_correlation(x:Sequence[float],y:Sequence[float])->float:
    a,b=_v(x),_v(y)
    if len(a)!=len(b) or len(a)<2:
        raise ValueError("correlation requires equal sequences with at least two observations")
    ma,mb=mean(a),mean(b)
    den=math.sqrt(sum((u-ma)**2 for u in a)*sum((v-mb)**2 for v in b))
    return 0.0 if den==0 else sum((u-ma)*(v-mb) for u,v in zip(a,b))/den
def linear_regression(x:Sequence[float],y:Sequence[float])->tuple[float,float,float]:
    a,b=_v(x),_v(y)
    if len(a)!=len(b) or len(a)<2:
        raise ValueError("regression requires equal sequences with at least two observations")
    mx,my=mean(a),mean(b)
    sxx=sum((u-mx)**2 for u in a)
    if sxx==0:
        return 0.0,my,0.0
    slope=sum((u-mx)*(v-my) for u,v in zip(a,b))/sxx
    intercept=my-slope*mx
    total=sum((v-my)**2 for v in b)
    residual=sum((v-(intercept+slope*u))**2 for u,v in zip(a,b))
    return slope,intercept,(1.0 if total==0 and residual==0 else 0.0 if total==0 else max(0.0,1.0-residual/total))
def describe(values:Sequence[float])->StatisticalMeasurement:
    r=_v(values)
    m=mean(r)
    sd=standard_deviation(r)
    x=[float(i) for i in range(len(r))]
    slope,intercept,r2=linear_regression(x,r) if len(r)>=2 else (None,None,None)
    return StatisticalMeasurement(len(r),m,variance(r),sd,min(r),max(r),0.0 if sd==0 else (r[-1]-m)/sd,pearson_correlation(x,r) if len(r)>=2 else None,slope,intercept,r2)
