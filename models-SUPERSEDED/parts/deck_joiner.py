from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rover import deck_joiner

def gen_step():
    return deck_joiner()
