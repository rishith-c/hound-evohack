from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rover import motor_mount

def gen_step():
    return motor_mount()
