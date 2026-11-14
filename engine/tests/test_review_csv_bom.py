import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_bom(tmp_path):
 p=tmp_path/'rows.csv'
 p.write_text('\ufeffid,problem_id,step1,true_step\nR1,f3-a1,t,1\n',encoding='utf-8')
 rows,errors=r.read_rows(p)
 assert not errors and rows[0].id=='R1'
