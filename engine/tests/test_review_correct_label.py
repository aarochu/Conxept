import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_contradictory_correct_label():
 o=r.evaluate_row(Row('R1','f3-a1','A',['t'],0,'other'))
 assert 'empty true_label' in o.input_error
