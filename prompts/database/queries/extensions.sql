-- Postgres extensions installed in this database.
select e.extname as name, e.extversion as version, n.nspname as schema,
       a.default_version as latest_version, a.comment
from pg_extension e
join pg_namespace n on n.oid = e.extnamespace
left join pg_available_extensions a on a.name = e.extname
order by e.extname;
