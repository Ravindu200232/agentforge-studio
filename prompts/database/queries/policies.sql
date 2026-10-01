-- Row level security policies: which table, which command, for whom, and the rule itself.
select schemaname as schema, tablename as table, policyname as name, permissive, roles, cmd as command,
       qual as using_expression, with_check as check_expression
from pg_policies
order by schemaname, tablename, policyname;
