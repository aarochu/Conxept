import pytest
import baseline as b

def test_score_length():
 with pytest.raises(ValueError,match='every sampled'): b.score([object()],[])
