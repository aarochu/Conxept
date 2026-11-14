import csv
from pathlib import Path
import pytest
import real_eval as r
from real_eval import Row

def test_excess_steps():
 o=r.evaluate_row(Row('R1','f3-a1','A',['t']*3,1,''))
 assert 'at most 2 steps' in o.input_error
