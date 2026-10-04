import pytest
from researchos.quant_math.matrix import dot,euclidean_distance_vector,matrix_multiply,transpose
from researchos.quant_math.mle import bernoulli_mle,normal_mle
from researchos.quant_math.multivariate import nearest_neighbors,normalize_minmax

def test_matrix_operations():
    assert matrix_multiply(((1,2),(3,4)),((2,0),(1,2)))==((4.0,4.0),(10.0,8.0))
    assert transpose(((1,2,3),(4,5,6)))==((1.0,4.0),(2.0,5.0),(3.0,6.0))
    assert dot((1,2),(3,4))==11
    assert euclidean_distance_vector((0,0),(3,4))==5

def test_mle():
    assert normal_mle([1,2,3])==(pytest.approx(2.0),pytest.approx(2/3))
    assert bernoulli_mle(7,10)==pytest.approx(.7)

def test_multivariate_is_deterministic():
    rows=normalize_minmax(((0,10),(5,20),(10,30)))
    assert rows[0]==(0.0,0.0)
    assert nearest_neighbors((0.1,0.1),rows,2)[0][0]==0
