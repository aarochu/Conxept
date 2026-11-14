import pytest
import baseline as b

def test_mismatched_runs():
 with pytest.raises(ValueError,match='same number'): b.disagreements([1],[])
 assert b.disagreements([1,2],[1,3])==1
