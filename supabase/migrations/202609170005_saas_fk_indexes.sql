-- Cover foreign keys used by tenant filtering, joins, and cascading changes.
create index if not exists idx_dataset_created_by on public.dataset(created_by);
create index if not exists idx_dataset_version_created_by on public.dataset_version(created_by);
create index if not exists idx_dataset_version_dataset_id on public.dataset_version(dataset_id);
create index if not exists idx_research_run_dataset_version_id on public.research_run(dataset_version_id);
create index if not exists idx_research_run_created_by on public.research_run(created_by);
create index if not exists idx_artifact_workspace_id on public.artifact(workspace_id);
create index if not exists idx_evidence_workspace_id on public.evidence(workspace_id);
create index if not exists idx_evidence_artifact_id on public.evidence(artifact_id);
create index if not exists idx_usage_event_user_id on public.usage_event(user_id);
create index if not exists idx_usage_event_research_run_id on public.usage_event(research_run_id);
create index if not exists idx_audit_log_workspace_id on public.audit_log(workspace_id);
create index if not exists idx_audit_log_user_id on public.audit_log(user_id);
