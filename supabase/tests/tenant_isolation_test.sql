-- R3 adversarial tenant-isolation tests.
-- The fixture is fully transactional. Grants are temporarily widened inside
-- the transaction so the tests exercise RLS independently of the production
-- server-only Data API boundary; the transaction rolls back all changes.
begin;

select plan(23);

insert into auth.users (id, email)
values
  ('11111111-1111-1111-1111-111111111111', 'qros-tenant-a@test.invalid'),
  ('22222222-2222-2222-2222-222222222222', 'qros-tenant-b@test.invalid');

insert into public.workspace (id, name)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'QROS tenant A'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'QROS tenant B');

insert into public.workspace_member (workspace_id, user_id, role)
values
  ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', '11111111-1111-1111-1111-111111111111', 'owner'),
  ('bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', '22222222-2222-2222-2222-222222222222', 'owner');

insert into public.dataset (id, workspace_id, name, created_by)
values
  ('aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'dataset-a', '11111111-1111-1111-1111-111111111111'),
  ('bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb', 'dataset-b', '22222222-2222-2222-2222-222222222222');

insert into public.dataset_version
  (id, dataset_id, version_no, content_sha256, storage_path, byte_size, created_by)
values
  ('aaaaaaaa-1000-0000-0000-aaaaaaaaaaaa', 'aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa', 1,
   repeat('a', 64), 'qros/a.csv', 1, '11111111-1111-1111-1111-111111111111'),
  ('bbbbbbbb-1000-0000-0000-bbbbbbbbbbbb', 'bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb', 1,
   repeat('b', 64), 'qros/b.csv', 1, '22222222-2222-2222-2222-222222222222');

insert into public.research_run
  (id, workspace_id, dataset_version_id, workflow_id, status, created_by, source_dataset_sha256)
values
  ('aaaaaaaa-2000-0000-0000-aaaaaaaaaaaa', 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
   'aaaaaaaa-1000-0000-0000-aaaaaaaaaaaa', 'fixture-a', 'queued',
   '11111111-1111-1111-1111-111111111111', repeat('a', 64)),
  ('bbbbbbbb-2000-0000-0000-bbbbbbbbbbbb', 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
   'bbbbbbbb-1000-0000-0000-bbbbbbbbbbbb', 'fixture-b', 'queued',
   '22222222-2222-2222-2222-222222222222', repeat('b', 64));

-- Exercise RLS directly. Production intentionally has no anon/authenticated
-- table grants; those grants are temporary and rolled back at the end.
grant select, insert, update, delete on
  public.workspace, public.workspace_member, public.dataset,
  public.dataset_version, public.research_run, public.artifact,
  public.evidence, public.usage_event, public.audit_log
to authenticated;

set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

select results_eq(
  $$select count(*)::bigint from public.workspace$$,
  $$values (1::bigint)$$,
  'tenant A sees only its workspace'
);

select results_eq(
  $$select count(*)::bigint from public.dataset$$,
  $$values (1::bigint)$$,
  'tenant A sees only its dataset'
);

select results_eq(
  $$select count(*)::bigint from public.dataset_version$$,
  $values (1::bigint)$,
  'tenant A sees only its dataset version'
);

select results_eq(
  $$select count(*)::bigint from public.research_run$$,
  $values (1::bigint)$,
  'tenant A sees only its research run'
);

select is_empty(
  $$select name from public.dataset where id = 'bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb'$$,
  'tenant A cannot read tenant B dataset by resource id'
);

select throws_ok(
  $$insert into public.dataset(id, workspace_id, name, created_by)
    values ('aaaaaaaa-0001-0000-0000-aaaaaaaaaaaa',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'cross-tenant-write',
            '11111111-1111-1111-1111-111111111111')$$,
  '42501',
  null,
  'tenant A cannot insert into tenant B'
);

select is_empty(
  $$update public.dataset
       set name = 'tampered'
     where id = 'bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb'
     returning id$$,
  'tenant A cannot update tenant B'
);

select throws_ok(
  $$insert into public.dataset_version
      (id, dataset_id, version_no, content_sha256, storage_path, byte_size, created_by)
    values ('aaaaaaaa-1001-0000-0000-aaaaaaaaaaaa',
            'bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb', 2,
            repeat('c', 64), 'qros/c.csv', 1,
            '11111111-1111-1111-1111-111111111111')$$,
  '42501',
  null,
  'tenant A cannot create a version under tenant B dataset'
);

select is_empty(
  $$select id from public.research_run
     where id = 'bbbbbbbb-2000-0000-0000-bbbbbbbbbbbb'$$,
  'tenant A cannot observe tenant B run by id'
);

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

select results_eq(
  $$select count(*)::bigint from public.workspace$$,
  $values (1::bigint)$,
  'tenant B sees only its workspace'
);

select results_eq(
  $$select count(*)::bigint from public.dataset$$,
  $values (1::bigint)$,
  'tenant B sees only its dataset'
);

select is_empty(
  $$select name from public.dataset where id = 'aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa'$$,
  'tenant B cannot read tenant A dataset by resource id'
);

select is_empty(
  $$update public.dataset
       set name = 'tampered-by-b'
     where id = 'aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa'
     returning id$$,
  'tenant B cannot update tenant A'
);

-- Integrity triggers must also reject mismatched child references when a
-- trusted server-side writer bypasses RLS.
set local role postgres;

select throws_ok(
  $$insert into public.research_run
      (id, workspace_id, dataset_version_id, workflow_id, status, created_by, source_dataset_sha256)
    values ('bbbbbbbb-2001-0000-0000-bbbbbbbbbbbb',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'aaaaaaaa-1000-0000-0000-aaaaaaaaaaaa',
            'cross-run', 'queued',
            '22222222-2222-2222-2222-222222222222', repeat('a', 64))$$,
  'P0001',
  'research run workspace mismatch',
  'trusted writer cannot cross-bind a research run to another tenant'
);

select throws_ok(
  $$insert into public.artifact
      (id, workspace_id, research_run_id, kind, content_sha256, storage_path, byte_size)
    values ('bbbbbbbb-3000-0000-0000-bbbbbbbbbbbb',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'aaaaaaaa-2000-0000-0000-aaaaaaaaaaaa',
            'report', repeat('c', 64), 'qros/c', 1)$$,
  'P0001',
  'research child workspace mismatch',
  'trusted writer cannot cross-bind an artifact to another tenant'
);

select throws_ok(
  $$insert into public.evidence
      (id, workspace_id, research_run_id, claim, status)
    values ('bbbbbbbb-4000-0000-0000-bbbbbbbbbbbb',
            'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
            'aaaaaaaa-2000-0000-0000-aaaaaaaaaaaa',
            'cross-tenant claim', 'unverified')$$,
  'P0001',
  'research child workspace mismatch',
  'trusted writer cannot cross-bind evidence to another tenant'
);

select is(
  has_function_privilege(
    'authenticated',
    'public.create_research_run_idempotent(uuid,uuid,uuid,text,uuid,text,text,jsonb)',
    'EXECUTE'
  ),
  false,
  'authenticated cannot execute privileged idempotent research-run RPC'
);

select is(
  has_function_privilege(
    'authenticated',
    'public.enqueue_research_run(uuid,uuid)',
    'EXECUTE'
  ),
  false,
  'authenticated cannot execute privileged enqueue RPC'
);

select is(
  has_function_privilege(
    'authenticated',
    'public.finish_research_run(uuid,uuid,uuid,text,text)',
    'EXECUTE'
  ),
  false,
  'authenticated cannot execute privileged finish RPC'
);


set local role authenticated;
set local request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';

select throws_ok(
  $$
    update public.dataset
       set workspace_id = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
     where id = 'aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa'
  $$,
  '42501',
  null,
  'tenant A cannot rebind its dataset to tenant B'
);

select is(
  (select count(*) from public.dataset
    where workspace_id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'),
  1::bigint,
  'tenant A dataset remains in tenant A after workspace-id injection attempt'
);

select results_eq(
  $$with deleted as (
      delete from public.dataset
       where id = 'bbbbbbbb-0000-0000-0000-bbbbbbbbbbbb'
       returning id
    )
    select count(*)::bigint from deleted$$,
  $$values (0::bigint)$$,
  'tenant A cannot delete tenant B dataset by resource id'
);

set local request.jwt.claim.sub = '22222222-2222-2222-2222-222222222222';

select results_eq(
  $$with deleted as (
      delete from public.dataset
       where id = 'aaaaaaaa-0000-0000-0000-aaaaaaaaaaaa'
       returning id
    )
    select count(*)::bigint from deleted$$,
  $$values (0::bigint)$$,
  'tenant B cannot delete tenant A dataset by resource id'
);

select * from finish();
rollback;

