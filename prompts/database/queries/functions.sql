-- Database functions and triggers the application defined (outside Supabase's own schemas).
select n.nspname as schema, p.proname as name, pg_get_function_identity_arguments(p.oid) as arguments,
       pg_get_function_result(p.oid) as returns, l.lanname as language,
       case p.prosecdef when true then 'definer' else 'invoker' end as security,
       (select count(*) from pg_trigger t where t.tgfoid = p.oid and not t.tgisinternal) as triggers
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
join pg_language l on l.oid = p.prolang
where n.nspname not in ('pg_catalog', 'information_schema', 'auth', 'storage', 'realtime', 'extensions', 'graphql',
                        'graphql_public', 'vault', 'net', 'pgsodium', 'supabase_functions', 'cron', 'pgbouncer')
  and n.nspname not like 'pg\_%'
  and p.prokind in ('f', 'p')
order by n.nspname, p.proname;
