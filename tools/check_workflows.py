from __future__ import annotations

import pathlib
import re
import sys

import yaml


VERSIONED_WORKFLOW = re.compile(r"-v\d+\.ya?ml$")


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML mapping keys instead of silently overwriting them."""


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def main() -> int:
    bad: list[str] = []
    workflow_dir = pathlib.Path(".github/workflows")
    workflow_names: dict[str, str] = {}

    for path in sorted(workflow_dir.glob("*.y*ml")):
        if VERSIONED_WORKFLOW.search(path.name):
            bad.append(f"{path.name}: versioned workflow names are forbidden")
        try:
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except yaml.YAMLError as exc:
            bad.append(f"{path.name}: invalid YAML ({exc})")
            continue
        if not isinstance(data, dict) or "name" not in data:
            bad.append(f"{path.name}: missing top-level 'name'")
            continue

        workflow_name = str(data["name"])
        previous = workflow_names.get(workflow_name)
        if previous is not None:
            bad.append(
                f"{path.name}: duplicate workflow name {workflow_name!r} "
                f"(already defined by {previous})"
            )
        else:
            workflow_names[workflow_name] = path.name

    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1

    print(f"workflow hygiene: clean ({len(workflow_names)} unique workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
