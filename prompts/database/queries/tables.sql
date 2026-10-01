-- Every table and partitioned table: where it lives, how big it is, and how it is protected.
select
  n.nspname as schema,
  c.relname as name,
  greatest(c.reltuples, 0)::bigint as estimated_rows,
  coalesce(s.n_live_tup, 0)::bigint as live_rows,
  pg_total_relation_size(c.oid) as total_bytes,
  pg_relation_size(c.oid) as table_bytes,
  pg_indexes_size(c.oid) as index_bytes,
  c.relrowsecurity as rls_enabled,
  (select count(*) from pg_policies p where p.schemaname = n.nspname and p.tablename = c.relname) as policies,
  (select count(*) from information_schema.columns col
    where col.table_schema = n.nspname and col.table_name = c.relname) as columns,
  n.nspname not in ('public') and n.nspname in (
    'auth', 'storage', 'realtime', 'supabase_functions', 'supabase_migrations', 'extensions', 'graphql',
    'graphql_public', 'vault', 'net', 'pgsodium', 'pgsodium_masks', 'cron', 'pgbouncer', 'pgtle', '_realtime',
    '_analytics', 'topology') as system,
  obj_description(c.oid, 'pg_class') as comment
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
left join pg_stat_user_tables s on s.relid = c.oid
where c.relkind in ('r', 'p')
  and n.nspname not in ('pg_catalog', 'information_schema')
  and n.nspname not like 'pg\_%'
order by system, n.nspname, c.relname;
