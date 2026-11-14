import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE / "gen"))
sys.path.insert(0, str(ENGINE))
