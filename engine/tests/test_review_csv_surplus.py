import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_empty_surplus(tmp_path):
 p=tmp_path/'rows.csv'; p.write_text('id,problem_id,step1,true_step\nR1,f3-a1,t,1,\n')
 rows,errors=r.read_rows(p)
 assert not rows and 'too many columns' in errors[0]
