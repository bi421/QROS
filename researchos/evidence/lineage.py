"""
LineageQueryEngine — read-only lineage query layer.

Phase 5.3c Step 2 — Lineage Query Engine implementation.

This module provides a read-only query API over the existing
``EvidenceRepository`` lineage graph (its ``evidence`` and ``lineage``
tables). It is strictly additive:

    - ``explain(artifact_hash)``    — full provenance (artifact, parents,
      children, type, lineage path).
    - ``ancestors(artifact_hash)``  — all parent artifacts, recursively.
    - ``descendants(artifact_hash)``— all child artifacts, recursively.
    - ``lineage_tree(artifact_hash)`` — structured Dataset → Experiment → Run →
      Result → Validation tree.
    - ``resolve_reference(hash)``   — resolve payload references
      (dataset_version / experiment_hash / run_hash / result_hash /
      validation_hash).
    - ``resolve_full_chain(result_hash)`` — return Dataset, Experiment, Run,
      Result, Validation.
    - ``path(parent_hash, child_hash)`` — return a lineage path between
      artifacts.

Design principles:
    - READ-ONLY: traversal never writes, never mutates the repository, never
      emits new artifacts.
    - Deterministic ordering: results are sorted by ``artifact_hash`` so
      identical stores always yield identical query output.
    - Cycle-safe: every recursive traversal tracks a visited set; a cycle
      aborts the traversal for that branch (defensive, since the lineage table
      is a DAG by construction).
    - Tamper-aware: every returned node is checked with ``envelope.verify()``;
      a tampered artifact is surfaced (``verified=False``) rather than silently
      trusted.

This is a certification/trust/query layer only — it computes no trading
decisions and performs no execution.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from researchos.evidence.envelope import EvidenceEnvelope
from researchos.evidence.repository import EvidenceRepository

#: Canonical artifact type order for the lineage tree / full chain.
_CHAIN_ORDER = ("Dataset", "Experiment", "Run", "Result", "Validation")


@dataclass(frozen=True)
class LineageNode:
    """A single artifact node in a lineage result.

    Attributes:
        artifact: The evidence envelope.
        artifact_hash: The artifact's canonical hash.
        artifact_type: The artifact type (e.g. "Result").
        verified: True when the envelope passes ``verify()``.
    """

    artifact: EvidenceEnvelope
    artifact_hash: str
    artifact_type: str
    verified: bool

    @classmethod
    def from_envelope(cls, envelope: EvidenceEnvelope) -> LineageNode:
        return cls(
            artifact=envelope,
            artifact_hash=envelope.artifact_hash,
            artifact_type=envelope.artifact_type,
            verified=envelope.verify(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_hash": self.artifact_hash,
            "artifact_type": self.artifact_type,
            "verified": self.verified,
        }


@dataclass(frozen=True)
class LineageExplanation:
    """Complete provenance explanation for a single artifact.

    Attributes:
        artifact: The target envelope.
        artifact_type: The target artifact type.
        parents: Ordered parent ``LineageNode`` objects.
        children: Ordered child ``LineageNode`` objects.
        lineage_path: The canonical lineage path (list of artifact hashes from
            the earliest ancestor to the target).
    """

    artifact: EvidenceEnvelope
    artifact_type: str
    parents: tuple[LineageNode, ...]
    children: tuple[LineageNode, ...]
    lineage_path: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_hash": self.artifact.artifact_hash,
            "artifact_type": self.artifact_type,
            "parents": [p.to_dict() for p in self.parents],
            "children": [c.to_dict() for c in self.children],
            "lineage_path": list(self.lineage_path),
        }


@dataclass(frozen=True)
class LineageTreeNode:
    """A node in the recursive lineage tree.

    Attributes:
        node: The ``LineageNode`` for this artifact.
        parents: Recursive parent nodes (upstream).
        children: Recursive child nodes (downstream).
    """

    node: LineageNode
    parents: tuple[LineageTreeNode, ...] = field(default_factory=tuple)
    children: tuple[LineageTreeNode, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node.to_dict(),
            "parents": [p.to_dict() for p in sorted(self.parents, key=lambda n: n.node.artifact_hash)],
            "children": [c.to_dict() for c in sorted(self.children, key=lambda n: n.node.artifact_hash)],
        }


@dataclass(frozen=True)
class FullChain:
    """The resolved Dataset → Experiment → Run → Result → Validation chain.

    Each member is ``None`` when not resolvable for the queried artifact.
    """

    dataset: EvidenceEnvelope | None = None
    experiment: EvidenceEnvelope | None = None
    run: EvidenceEnvelope | None = None
    result: EvidenceEnvelope | None = None
    validation: EvidenceEnvelope | None = None

    def to_dict(self) -> dict[str, Any]:
        def _h(e: EvidenceEnvelope | None) -> str | None:
            return e.artifact_hash if e is not None else None

        return {
            "dataset": _h(self.dataset),
            "experiment": _h(self.experiment),
            "run": _h(self.run),
            "result": _h(self.result),
            "validation": _h(self.validation),
        }


def _sorted_hashes(hashes: Iterable[str]) -> list[str]:
    """Return a deterministically sorted list of hashes."""
    return sorted(list(hashes))


class LineageQueryEngine:
    """Read-only lineage query facade over an ``EvidenceRepository``."""

    def __init__(self, repository: EvidenceRepository | None = None) -> None:
        self._repo = repository or EvidenceRepository()

    # ── primitive accessors ────────────────────────────────────────────

    def _get(self, artifact_hash: str) -> EvidenceEnvelope | None:
        return self._repo.get_artifact(artifact_hash)

    def _parents_of(self, artifact_hash: str) -> list[str]:
        return _sorted_hashes(self._repo.get_parents(artifact_hash))

    def _children_of(self, artifact_hash: str) -> list[str]:
        return _sorted_hashes(self._repo.get_children(artifact_hash))

    # ── ancestors / descendants (recursive, cycle-safe) ────────────────

    def ancestors(self, artifact_hash: str) -> tuple[EvidenceEnvelope, ...]:
        """Return all parent artifacts recursively (upstream, deterministic).

        The result is a tuple of envelopes ordered by ``artifact_hash``.
        A missing artifact returns an empty tuple.  Cycles are safely
        terminated via a visited set.
        """
        if self._get(artifact_hash) is None:
            return ()
        visited: set = set()
        result: dict[str, EvidenceEnvelope] = {}
        queue: list[str] = list(self._parents_of(artifact_hash))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            env = self._get(current)
            if env is not None:
                result[current] = env
                queue.extend(self._parents_of(current))
        return tuple(result[h] for h in _sorted_hashes(result.keys()))

    def descendants(self, artifact_hash: str) -> tuple[EvidenceEnvelope, ...]:
        """Return all child artifacts recursively (downstream, deterministic)."""
        if self._get(artifact_hash) is None:
            return ()
        visited: set = set()
        result: dict[str, EvidenceEnvelope] = {}
        queue: list[str] = list(self._children_of(artifact_hash))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            env = self._get(current)
            if env is not None:
                result[current] = env
                queue.extend(self._children_of(current))
        return tuple(result[h] for h in _sorted_hashes(result.keys()))

    # ── lineage path (BFS shortest through the graph) ──────────────────

    def path(self, parent_hash: str, child_hash: str) -> tuple[str, ...]:
        """Return a lineage path (list of hashes) between two artifacts.

        The path is found via BFS over the undirected edge set (so it works
        for either ancestor→descendant or descendant→ancestor directions) and
        returned as a deterministic tuple of hashes, or ``()`` when no path
        exists.
        """
        if self._get(parent_hash) is None or self._get(child_hash) is None:
            return ()
        if parent_hash == child_hash:
            return (parent_hash,)
        # Build adjacency from both directions.
        adj: dict[str, list[str]] = {}

        def _add(u: str, v: str) -> None:
            adj.setdefault(u, []).append(v)

        # Seed with the two endpoints' edges, then walk the whole reachable set.
        frontier = [parent_hash, child_hash]
        visited_seed: set = set()
        while frontier:
            cur = frontier.pop(0)
            if cur in visited_seed:
                continue
            visited_seed.add(cur)
            for n in self._parents_of(cur) + self._children_of(cur):
                _add(cur, n)
                if n not in visited_seed:
                    frontier.append(n)
        # BFS from parent_hash to child_hash.
        prev: dict[str, str] = {}
        seen: set = {parent_hash}
        queue = [parent_hash]
        while queue:
            cur = queue.pop(0)
            if cur == child_hash:
                path = [cur]
                while cur != parent_hash:
                    cur = prev[cur]
                    path.append(cur)
                return tuple(reversed(path))
            for nxt in adj.get(cur, []):
                if nxt not in seen:
                    seen.add(nxt)
                    prev[nxt] = cur
                    queue.append(nxt)
        return ()

    # ── explain ────────────────────────────────────────────────────────

    def explain(self, artifact_hash: str) -> LineageExplanation | None:
        """Return a complete provenance explanation for an artifact.

        Returns ``None`` when the artifact is not present in the store.
        """
        env = self._get(artifact_hash)
        if env is None:
            return None
        parents = tuple(LineageNode.from_envelope(self._get(h)) for h in self._parents_of(artifact_hash))
        children = tuple(LineageNode.from_envelope(self._get(h)) for h in self._children_of(artifact_hash))
        lineage_path = self._lineage_path_hashes(artifact_hash)
        return LineageExplanation(
            artifact=env,
            artifact_type=env.artifact_type,
            parents=parents,
            children=children,
            lineage_path=lineage_path,
        )

    def _lineage_path_hashes(self, artifact_hash: str) -> tuple[str, ...]:
        """Return the canonical lineage path for an artifact.

        The path is the sorted list of ancestors (including the artifact
        itself last), ordered deterministically by artifact type then hash.
        """
        ancestors: dict[str, EvidenceEnvelope] = {a.artifact_hash: a for a in self.ancestors(artifact_hash)}
        self_env = self._get(artifact_hash)
        if self_env is not None:
            ancestors[artifact_hash] = self_env
        ordered = sorted(
            ancestors.values(),
            key=lambda e: (
                _CHAIN_ORDER.index(e.artifact_type) if e.artifact_type in _CHAIN_ORDER else len(_CHAIN_ORDER),
                e.artifact_hash,
            ),
        )
        return tuple(e.artifact_hash for e in ordered)

    # ── lineage_tree ───────────────────────────────────────────────────

    def lineage_tree(self, artifact_hash: str) -> LineageTreeNode | None:
        """Return a structured recursive lineage tree rooted at ``artifact_hash``.

        The tree contains both parents (upstream) and children (downstream),
        cycle-safe.  Returns ``None`` when the artifact is not present.
        """
        env = self._get(artifact_hash)
        if env is None:
            return None
        root = LineageNode.from_envelope(env)
        parent_nodes = self._tree_nodes(self._parents_of(artifact_hash), set([artifact_hash]))
        child_nodes = self._tree_nodes(self._children_of(artifact_hash), set([artifact_hash]))
        return LineageTreeNode(node=root, parents=parent_nodes, children=child_nodes)

    def _tree_nodes(
        self,
        hashes: Sequence[str],
        visited: set,
    ) -> tuple[LineageTreeNode, ...]:
        out: list[LineageTreeNode] = []
        for h in _sorted_hashes(hashes):
            if h in visited:
                continue
            env = self._get(h)
            if env is None:
                continue
            node = LineageNode.from_envelope(env)
            new_visited = set(visited)
            new_visited.add(h)
            parents = self._tree_nodes(self._parents_of(h), new_visited)
            children = self._tree_nodes(self._children_of(h), new_visited)
            out.append(LineageTreeNode(node=node, parents=parents, children=children))
        return tuple(out)

    # ── resolve_reference ──────────────────────────────────────────────

    def resolve_reference(self, artifact_hash: str) -> dict[str, Any]:
        """Resolve the payload references of an artifact.

        Given an artifact, scan its payload for the reference keys
        (``dataset_version``, ``experiment_hash``, ``run_hash``,
        ``result_hash``, ``validation_hash``) and resolve each into the
        referenced envelope.

        Resolution order per reference key:
            1. The payload's own value is looked up directly in the store
               (when that value is itself a stored artifact hash).
            2. Otherwise the reference is resolved through the lineage edges
               (parents for upstream artifact types, children for the
               downstream Validation) that carry the explicitly-named
               reference type.

        Returns a mapping of reference key → resolved envelope (or, for
        ``dataset_version``, the Dataset ``version`` string), with ``None``
        when not resolvable.
        """
        env = self._get(artifact_hash)
        if env is None:
            return {}
        payload = env.payload
        if not isinstance(payload, Mapping):
            return {}
        out: dict[str, Any] = {}
        # A Dataset artifact carries its version under the "version" key;
        # expose that as the derived "dataset_version" reference.
        if env.artifact_type == "Dataset" and "version" in payload:
            out["dataset_version"] = str(payload["version"])

        # Map each reference key to the artifact_type it denotes.
        type_by_key = {
            "experiment_hash": "Experiment",
            "run_hash": "Run",
            "result_hash": "Result",
            "validation_hash": "Validation",
        }
        ref_keys = (
            "dataset_version",
            "experiment_hash",
            "run_hash",
            "result_hash",
            "validation_hash",
        )
        for key in ref_keys:
            if key in type_by_key:
                target_type = type_by_key[key]
                # 1) Direct payload value lookup.
                raw = payload.get(key)
                if raw:
                    direct = self._get(str(raw))
                    if direct is not None and direct.artifact_type == target_type:
                        out[key] = direct
                        continue
                # 2) Resolve through lineage edges by artifact type.
                out[key] = self._find_reference_by_type(env, target_type, upstream=target_type != "Validation")
            elif key == "dataset_version":
                if key not in out:
                    raw = payload.get(key)
                    out[key] = str(raw) if raw else None
        return out

    def _find_reference_by_type(self, env: EvidenceEnvelope, target_type: str, upstream: bool) -> EvidenceEnvelope | None:
        """Find a reference envelope of ``target_type`` among the artifact's
        lineage neighbors (upstream parents or downstream children)."""
        if upstream:
            for parent_hash in self._parents_of(env.artifact_hash):
                parent = self._get(parent_hash)
                if parent is not None and parent.artifact_type == target_type:
                    return parent
            for anc in self.ancestors(env.artifact_hash):
                if anc.artifact_type == target_type:
                    return anc
        else:
            for child_hash in self._children_of(env.artifact_hash):
                child = self._get(child_hash)
                if child is not None and child.artifact_type == target_type:
                    return child
            for desc in self.descendants(env.artifact_hash):
                if desc.artifact_type == target_type:
                    return desc
        return None

    # ── resolve_full_chain ─────────────────────────────────────────────

    def resolve_full_chain(self, result_hash: str) -> FullChain | None:
        """Resolve the Dataset → Experiment → Run → Result → Validation chain.

        Starting from a ``Result`` artifact hash, walk upstream via lineage
        edges (preferring the canonical artifact type) to find the Run,
        Experiment, and Dataset, and downstream to find the Validation.

        Returns a ``FullChain`` with the resolved envelopes (``None`` for any
        member that cannot be resolved), or ``None`` when ``result_hash`` is
        not a Result artifact.
        """
        result = self._get(result_hash)
        if result is None or result.artifact_type != "Result":
            return None

        # Run: parent(s) of the Result with artifact_type "Run".
        run = self._find_parent_of_type(result_hash, "Run")

        # Experiment: parent(s) of the Run with artifact_type "Experiment".
        experiment: EvidenceEnvelope | None = None
        if run is not None:
            experiment = self._find_parent_of_type(run.artifact_hash, "Experiment")

        # Dataset: parent(s) of the Experiment with artifact_type "Dataset".
        dataset: EvidenceEnvelope | None = None
        if experiment is not None:
            dataset = self._find_parent_of_type(experiment.artifact_hash, "Dataset")

        # Validation: child of the Result with artifact_type "Validation".
        validation = self._find_child_of_type(result_hash, "Validation")

        return FullChain(
            dataset=dataset,
            experiment=experiment,
            run=run,
            result=result,
            validation=validation,
        )

    def _find_parent_of_type(self, artifact_hash: str, artifact_type: str) -> EvidenceEnvelope | None:
        for parent_hash in self._parents_of(artifact_hash):
            env = self._get(parent_hash)
            if env is not None and env.artifact_type == artifact_type:
                return env
        # Fallback: search recursively through ancestors.
        for anc in self.ancestors(artifact_hash):
            if anc.artifact_type == artifact_type:
                return anc
        return None

    def _find_child_of_type(self, artifact_hash: str, artifact_type: str) -> EvidenceEnvelope | None:
        for child_hash in self._children_of(artifact_hash):
            env = self._get(child_hash)
            if env is not None and env.artifact_type == artifact_type:
                return env
        for desc in self.descendants(artifact_hash):
            if desc.artifact_type == artifact_type:
                return desc
        return None


__all__ = [
    "FullChain",
    "LineageExplanation",
    "LineageNode",
    "LineageQueryEngine",
    "LineageTreeNode",
]
