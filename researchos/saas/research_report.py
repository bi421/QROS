"""Deterministic, evidence-preserving research report projection.

This module is a presentation boundary only. It never computes scientific
claims and never changes the governed result status.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from researchos.saas.evidence_api import ResearchEvidenceRecord
from researchos.saas.provenance import ResearchRunResultRecord


@dataclass(frozen=True)
class ResearchReport:
    """Immutable human-readable projection of one governed research run."""

    schema: str
    workspace_id: UUID
    research_run_id: UUID
    status: str
    source_dataset_sha256: str
    manifest_sha256: str
    markdown: str
    report_sha256: str


def _line(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("\n", " ").strip()


def render_research_report(
    record: ResearchRunResultRecord,
    evidence: tuple[ResearchEvidenceRecord, ...],
) -> str:
    """Render stable Markdown without interpreting or upgrading evidence."""
    lines = [
        "# QROS Research Report",
        "",
        "## Run identity",
        "",
        f"- Schema: `qros-research-report.v1`",
        f"- Workspace: `{record.workspace_id}`",
        f"- Research run: `{record.research_run_id}`",
        f"- Status: **{_line(record.status)}**",
        f"- Source dataset SHA-256: `{_line(record.source_dataset_sha256)}`",
        f"- Result manifest SHA-256: `{_line(record.manifest_sha256)}`",
        "",
        "## Artifacts",
        "",
    ]
    if record.artifacts:
        for artifact in sorted(
            record.artifacts,
            key=lambda item: (item.artifact_id, item.kind, item.content_sha256),
        ):
            lines.append(
                f"- `{_line(artifact.artifact_id)}` — "
                f"{_line(artifact.kind)} — SHA-256 `{_line(artifact.content_sha256)}`"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Evidence lineage", ""])
    if evidence:
        for row in sorted(evidence, key=lambda item: str(item.id)):
            artifact = f" \\| artifact `{row.artifact_id}`" if row.artifact_id else ""
            lines.append(
                f"- `{row.id}` — status **{_line(row.status)}** — "
                f"{_line(row.claim)}{artifact}"
            )
    else:
        lines.append("- No evidence records were attached to this run.")
    lines.extend(["", "## Failures", ""])
    if record.failures:
        lines.extend(f"- {_line(failure)}" for failure in record.failures)
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Governance note",
            "",
            "This report is a deterministic presentation of the governed result "
            "and stored evidence lineage. It does not infer causality, profitability, "
            "statistical significance, or a positive finding.",
            "",
        ]
    )
    return "\n".join(lines)


def build_research_report(
    record: ResearchRunResultRecord,
    evidence: list[ResearchEvidenceRecord] | tuple[ResearchEvidenceRecord, ...],
) -> ResearchReport:
    markdown = render_research_report(record, tuple(evidence))
    report_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return ResearchReport(
        schema="qros-research-report.v1",
        workspace_id=record.workspace_id,
        research_run_id=record.research_run_id,
        status=record.status,
        source_dataset_sha256=record.source_dataset_sha256,
        manifest_sha256=record.manifest_sha256,
        markdown=markdown,
        report_sha256=report_sha256,
    )


__all__ = ["ResearchReport", "build_research_report", "render_research_report"]
