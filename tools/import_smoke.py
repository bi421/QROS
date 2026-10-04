from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python tools/import_smoke.py <package>", file=sys.stderr)
        return 2

    package_name = sys.argv[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    try:
        root = importlib.import_module(package_name)
    except Exception as exc:
        print(f"{package_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    resolved = getattr(root, "__file__", None)
    if resolved is None or not Path(resolved).resolve().is_relative_to(ROOT):
        print(
            f"{package_name}: imported outside checkout: "
            f"resolved={resolved!r} checkout={ROOT}",
            file=sys.stderr,
        )
        return 1

    package_path = getattr(root, "__path__", None)
    if package_path is None:
        print(f"{package_name}: not a package", file=sys.stderr)
        return 1

    failed: list[str] = []
    for module_info in pkgutil.walk_packages(package_path, root.__name__ + "."):
        try:
            importlib.import_module(module_info.name)
        except Exception as exc:
            failed.append(f"{module_info.name}: {type(exc).__name__}: {exc}")

    if failed:
        print("\n".join(failed), file=sys.stderr)
        return 1

    print(f"all modules import: {package_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
