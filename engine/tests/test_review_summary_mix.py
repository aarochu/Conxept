import pytest
import baseline as b

def test_actual_mix():
 sample=b.select_sample()[:1]
 model=[[b.ModelAnswer(0,'')]]; engine=[[b.EngineAnswer(0)]]
 text=b.summary_markdown(sample,'test','medium',model,engine)
 assert '(1 correct, 0 catalog errors, 0 held-out)' in text
