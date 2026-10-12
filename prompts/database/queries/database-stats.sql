-- The database as a whole: size, connections, cache hit rates and activity since the stats were reset.
select
  current_database() as name,
  version() as version,
  pg_database_size(current_database()) as database_bytes,
  (select count(*) from pg_stat_activity where datname = current_database()) as connections,
  (select setting::int from pg_settings where name = 'max_connections') as max_connections,
  (select round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2)
     from pg_stat_database where datname = current_database()) as cache_hit_percent,
  (select round(100.0 * sum(idx_blks_hit) / nullif(sum(idx_blks_hit) + sum(idx_blks_read), 0), 2)
     from pg_statio_user_indexes) as index_hit_percent,
  (select xact_commit from pg_stat_database where datname = current_database()) as commits,
  (select xact_rollback from pg_stat_database where datname = current_database()) as rollbacks,
  (select stats_reset from pg_stat_database where datname = current_database()) as stats_reset,
  (select count(*) from pg_namespace where nspname not like 'pg\_%' and nspname <> 'information_schema') as schemas,
  (select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where c.relkind in ('r', 'p') and n.nspname = 'public') as public_tables;
