import pytest
import baseline as b

from test_baseline import fake_client
@pytest.mark.parametrize('value',[True,1.9,'2',-1,7])
def test_invalid_model_step(value):
 ans=b.ask_model(fake_client(lambda _: {'first_wrong_step':value,'misconception':''}),'p','m','medium')
 assert ans.first_wrong_step==b.REFUSED and ans.error
