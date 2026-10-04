from __future__ import annotations

import pathlib
import re
import sys

import yaml


VERSIONED_WORKFLOW = re.compile(r"-v\d+\.ya?ml$")


def main() -> int:
    bad: list[str] = []
    workflow_dir = pathlib.Path(".github/workflows")

    for path in sorted(workflow_dir.glob("*.y*ml")):
        if VERSIONED_WORKFLOW.search(path.name):
            bad.append(f"{path.name}: versioned workflow names are forbidden")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            bad.append(f"{path.name}: invalid YAML ({exc})")
            continue
        if not isinstance(data, dict) or "name" not in data:
            bad.append(f"{path.name}: missing top-level 'name'")

    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1

    print("workflow hygiene: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
