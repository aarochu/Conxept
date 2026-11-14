import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_empty_split(tmp_path):
 p=tmp_path/'rows.csv'; p.write_text('id,problem_id,step1,true_step\n')
 out=tmp_path/'out'
 assert r.main([str(p),'--out',str(out)])==2
 assert not out.exists()
