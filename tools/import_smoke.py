from __future__ import annotations

import importlib
import pkgutil
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python tools/import_smoke.py <package>", file=sys.stderr)
        return 2

    package_name = sys.argv[1]
    try:
        root = importlib.import_module(package_name)
    except Exception as exc:
        print(f"{package_name}: {type(exc).__name__}: {exc}", file=sys.stderr)
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
