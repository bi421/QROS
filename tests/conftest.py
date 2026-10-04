from __future__ import annotations

from pathlib import Path

import researchos


ROOT = Path(__file__).resolve().parents[1]
RESEARCHOS_ROOT = Path(researchos.__file__).resolve()


def test_researchos_resolves_inside_checkout() -> None:
    assert RESEARCHOS_ROOT.is_relative_to(ROOT), (
        "researchos is resolving outside this checkout; "
        f"resolved={RESEARCHOS_ROOT} checkout={ROOT}"
    )
