-- QROS SaaS RLS performance hardening.
-- Preserve the canonical workspace-membership policies already established by
-- earlier migrations. Do not recreate legacy tenant_id policies: the governed
-- schema is workspace_id-based and several records are intentionally server-only.
-- A separate forward migration removes any legacy tenant_* policies that may
-- already exist in environments where the original version of this migration ran.

CREATE INDEX IF NOT EXISTS idx_billing_event_workspace_id
  ON public.billing_event (workspace_id);

CREATE INDEX IF NOT EXISTS idx_research_finding_research_run_id
  ON public.research_finding (research_run_id);

CREATE INDEX IF NOT EXISTS idx_research_finding_validation_id
  ON public.research_finding (validation_id);

CREATE INDEX IF NOT EXISTS idx_research_validation_research_run_id
  ON public.research_validation (research_run_id);
