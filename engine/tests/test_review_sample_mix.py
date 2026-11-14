import pytest
import baseline as b

@pytest.mark.parametrize('mix',[{}, {'unknown':1}, {'correct':-1}, {'correct':0}, {'correct':True}])
def test_invalid_sample_mix(mix):
 with pytest.raises(ValueError,match='sample mix'): b.select_sample(mix=mix)
