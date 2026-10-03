"""Legacy integration smoke probe retained for historical reference.

Use the maintained CI suites under researchos/ for authoritative tests.
This script is not part of the supported test surface.
"""

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))


def main() -> int:
    from researchos.strategy.grid_search_strategy import GridSearchStrategy

    strategy = GridSearchStrategy()
    results = strategy.run_grid_search([10, 20], [30, 70])
    if len(results) != 4:
        raise AssertionError(f"expected 4 results, got {len(results)}")
    print("legacy integration smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
