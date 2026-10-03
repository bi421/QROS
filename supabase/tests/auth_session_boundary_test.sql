begin;

select plan(5);

select has_function(
    'public',
    'qros_session_is_active',
    ARRAY['uuid', 'uuid'],
    'session revocation RPC exists'
);

select is(
    public.qros_session_is_active(
        '00000000-0000-0000-0000-000000000001'::uuid,
        '00000000-0000-0000-0000-000000000002'::uuid
    ),
    false,
    'unknown session is not active'
);

select is(
    has_function_privilege(
        'service_role',
        'public.qros_session_is_active(uuid,uuid)',
        'EXECUTE'
    ),
    true,
    'service_role can execute the session validation RPC'
);

select is(
    has_function_privilege(
        'anon',
        'public.qros_session_is_active(uuid,uuid)',
        'EXECUTE'
    ),
    false,
    'anon cannot execute the session validation RPC'
);

select is(
    has_function_privilege(
        'authenticated',
        'public.qros_session_is_active(uuid,uuid)',
        'EXECUTE'
    ),
    false,
    'authenticated cannot execute the session validation RPC'
);

select * from finish();
rollback;
