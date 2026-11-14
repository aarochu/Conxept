import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_inapplicable_label():
 o=r.evaluate_row(Row('R1','f3-a1','A',['t'],1,'dropped_shift_exponential'))
 assert 'family and step' in o.input_error
