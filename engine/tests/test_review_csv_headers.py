import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

@pytest.mark.parametrize('header',['id,problem_id,step1','id,problem_id,step1,true_step,id',''])
def test_headers(tmp_path,header):
 p=tmp_path/'rows.csv'; p.write_text(header+'\n')
 rows,errors=r.read_rows(p)
 assert not rows and errors and 'headers' in errors[0]
