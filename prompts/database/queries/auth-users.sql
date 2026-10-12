-- Who can sign in: totals, sign-in providers, and the most recent accounts.
select json_build_object(
  'total', (select count(*) from auth.users),
  'confirmed', (select count(*) from auth.users where email_confirmed_at is not null or phone_confirmed_at is not null),
  'signed_in_last_7_days', (select count(*) from auth.users where last_sign_in_at > now() - interval '7 days'),
  'created_last_7_days', (select count(*) from auth.users where created_at > now() - interval '7 days'),
  'anonymous', (select count(*) from auth.users where coalesce(is_anonymous, false)),
  'providers', (select coalesce(json_object_agg(provider, users), '{}'::json)
                  from (select provider, count(distinct user_id) as users from auth.identities group by provider) p),
  'recent', (select coalesce(json_agg(u), '[]'::json) from (
      select id, email, phone, created_at, last_sign_in_at,
             (email_confirmed_at is not null or phone_confirmed_at is not null) as confirmed,
             raw_app_meta_data ->> 'provider' as provider,
             coalesce(raw_app_meta_data -> 'providers', '[]'::jsonb) as providers,
             role
      from auth.users order by created_at desc limit 50) u)
) as users;
