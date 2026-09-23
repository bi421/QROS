begin;

select plan(4);

grant select, insert, update, delete on storage.objects to authenticated;

insert into storage.objects (id, bucket_id, name, owner_id)
values
  ('aaaaaaaa-5000-0000-0000-aaaaaaaaaaaa', 'qros-datasets',
   'tenant/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/datasets/' || repeat('a',64) || '/1/file.csv',
   '11111111-1111-1111-1111-111111111111'),
  ('bbbbbbbb-5000-0000-0000-bbbbbbbbbbbb', 'qros-datasets',
   'tenant/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/datasets/' || repeat('b',64) || '/1/file.csv',
   '22222222-2222-2222-2222-222222222222');

set local role authenticated;
set local request.jwt.claims = '{"sub":"11111111-1111-1111-1111-111111111111","role":"authenticated","tenant_id":"aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"}';

select results_eq(
  $$select count(*)::bigint from storage.objects
    where bucket_id = 'qros-datasets'$$,
  $$values (1::bigint)$$,
  'tenant A sees only tenant A objects'
);

select throws_ok(
  $$insert into storage.objects (id, bucket_id, name, owner_id)
    values ('aaaaaaaa-5001-0000-0000-aaaaaaaaaaaa', 'qros-datasets',
      'tenant/bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb/datasets/' || repeat('c',64) || '/1/file.csv',
      '11111111-1111-1111-1111-111111111111')$$,
  '42501',
  null,
  'tenant A cannot write tenant B object'
);

select throws_ok(
  $$insert into storage.objects (id, bucket_id, name, owner_id)
    values ('aaaaaaaa-5002-0000-0000-aaaaaaaaaaaa', 'qros-datasets',
      'datasets/' || repeat('d',64) || '/1/file.csv',
      '11111111-1111-1111-1111-111111111111')$$,
  '42501',
  null,
  'object without tenant prefix is rejected'
);

set local request.jwt.claims = '{"sub":"22222222-2222-2222-2222-222222222222","role":"authenticated","tenant_id":"bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"}';

select is_empty(
  $$select name from storage.objects
    where bucket_id = 'qros-datasets'
      and name like 'tenant/aaaaaaaa-%'$$,
  'tenant B cannot read tenant A object'
);

select * from finish();
rollback;
