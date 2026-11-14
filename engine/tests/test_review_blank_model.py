import pytest
import baseline as b

def test_blank_model():
 with pytest.raises(SystemExit) as exc: b.main(['--model','   '])
 assert exc.value.code==2
