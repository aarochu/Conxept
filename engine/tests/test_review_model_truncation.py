import pytest
import baseline as b

from types import SimpleNamespace as N

def test_truncated_response():
 response=N(stop_reason='max_tokens', model='m',content=[N(type='text',text='{"first_wrong_step":0,"misconception":""}')])
 client=N(beta=N(messages=N(create=lambda **kw:response)))
 ans=b.ask_model(client,'p','m','medium')
 assert ans.first_wrong_step==b.REFUSED and 'incomplete' in ans.error
