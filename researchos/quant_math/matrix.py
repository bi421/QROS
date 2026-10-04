from __future__ import annotations
from collections.abc import Sequence

MATRIX_VERSION="MATRIX_V1"
Matrix=tuple[tuple[float,...],...]

def _rect(a:Sequence[Sequence[float]])->Matrix:
    rows=tuple(tuple(float(x) for x in r) for r in a)
    if not rows or not rows[0] or any(len(r)!=len(rows[0]) for r in rows): raise ValueError("matrix must be non-empty and rectangular")
    return rows

def matrix_multiply(a:Sequence[Sequence[float]],b:Sequence[Sequence[float]])->Matrix:
    x,y=_rect(a),_rect(b)
    if len(x[0])!=len(y): raise ValueError("matrix dimensions are incompatible")
    return tuple(tuple(sum(x[i][k]*y[k][j] for k in range(len(y))) for j in range(len(y[0]))) for i in range(len(x)))

def transpose(a:Sequence[Sequence[float]])->Matrix:
    x=_rect(a); return tuple(tuple(x[i][j] for i in range(len(x))) for j in range(len(x[0])))

def dot(a:Sequence[float],b:Sequence[float])->float:
    if len(a)!=len(b) or not a: raise ValueError("vectors must have equal non-zero length")
    return sum(float(x)*float(y) for x,y in zip(a,b))

def euclidean_distance_vector(a:Sequence[float],b:Sequence[float])->float:
    if len(a)!=len(b) or not a: raise ValueError("vectors must have equal non-zero length")
    return sum((float(x)-float(y))**2 for x,y in zip(a,b))**0.5
