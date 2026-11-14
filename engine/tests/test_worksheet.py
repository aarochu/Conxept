from pathlib import Path

import worksheet


def test_default_output_is_inside_the_repo_regardless_of_cwd():
    repo = Path(__file__).resolve().parents[2]
    assert worksheet.DEFAULT_OUT == repo / "data" / "real" / "worksheet.md"
