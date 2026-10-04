from __future__ import annotations
import math
from collections.abc import Sequence
from researchos.quant_math.contracts import GeometryMeasurement,Vector2D

GEOMETRY_VERSION="MARKET_GEOMETRY_V1"

def _finite(values:Sequence[float])->list[float]:
    v=[float(x) for x in values]
    if not v or any(not math.isfinite(x) for x in v):
        raise ValueError("values must contain finite observations")
    return v

def _regression(x:Sequence[float],y:Sequence[float])->tuple[float,float,float]:
    if len(x)!=len(y) or len(x)<2:
        raise ValueError("regression requires equal sequences with at least two observations")
    mx=sum(x)/len(x)
    my=sum(y)/len(y)
    sxx=sum((z-mx)**2 for z in x)
    if sxx==0:
        return 0.0,my,0.0
    slope=sum((a-mx)*(b-my) for a,b in zip(x,y))/sxx
    intercept=my-slope*mx
    total=sum((b-my)**2 for b in y)
    residual=sum((b-(intercept+slope*a))**2 for a,b in zip(x,y))
    r2=1.0 if total==0 and residual==0 else (0.0 if total==0 else max(0.0,1.0-residual/total))
    return slope,intercept,r2

def vector_between(a:Vector2D,b:Vector2D)->Vector2D:
    return Vector2D(b.x-a.x,b.y-a.y)
def euclidean_distance(a:Vector2D,b:Vector2D)->float:
    return math.hypot(b.x-a.x,b.y-a.y)
def angle_of(v:Vector2D)->float:
    return math.atan2(v.y,v.x)

def curvature_three_points(a:Vector2D,b:Vector2D,c:Vector2D)->float:
    ab=vector_between(a,b)
    bc=vector_between(b,c)
    ac=vector_between(a,c)
    den=ab.magnitude()*bc.magnitude()*ac.magnitude()
    if den==0:
        return 0.0
    return 2.0*(ab.x*ac.y-ab.y*ac.x)/den

def _pivot_levels(p:Sequence[float])->tuple[float|None,float|None]:
    lows=[]
    highs=[]
    for i in range(1,len(p)-1):
        if p[i]<=p[i-1] and p[i]<=p[i+1]:
            lows.append(p[i])
        if p[i]>=p[i-1] and p[i]>=p[i+1]:
            highs.append(p[i])
    return (sum(lows)/len(lows) if lows else None,sum(highs)/len(highs) if highs else None)

def measure_market_geometry(prices:Sequence[float])->GeometryMeasurement:
    p=_finite(prices)
    if len(p)<2:
        raise ValueError("market geometry requires at least two prices")
    x=[float(i) for i in range(len(p))]
    slope,_,r2=_regression(x,p)
    v=Vector2D(x[-1]-x[0],p[-1]-p[0])
    angle=angle_of(v)
    curvature=curvature_three_points(Vector2D(x[-3],p[-3]),Vector2D(x[-2],p[-2]),Vector2D(x[-1],p[-1])) if len(p)>=3 else 0.0
    support,resistance=_pivot_levels(p)
    return GeometryMeasurement(slope,angle,math.degrees(angle),v.magnitude(),v,curvature,r2,support,resistance)
