import pytest
import baseline as b

import csv

def test_csv_provenance(tmp_path):
 sample=b.select_sample()[:1]; path=tmp_path/'out.csv'
 b.write_csv(path,sample,[[b.ModelAnswer(-1,'',served_by='fallback',refused=True,error='failed')]],[[b.EngineAnswer(0)]])
 row=next(csv.DictReader(path.open()))
 assert row['model_served_by_run1']=='fallback'
 assert row['model_refused_run1']=='True' and row['model_error_run1']=='failed'
