import sys
from pathlib import Path

# Make `import ml.eval` work when pytest runs from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
