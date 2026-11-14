import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_missing_csv(tmp_path,capsys):
 with pytest.raises(SystemExit) as exc: r.main([str(tmp_path/'missing.csv')])
 assert exc.value.code==2
 assert 'cannot read input CSV' in capsys.readouterr().err
