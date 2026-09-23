import sys

sys.path.insert(0, ".")
from researchos.auto_ml.runner import run_auto_ml

if __name__ == "__main__":
    run_auto_ml(n_trials=50)
