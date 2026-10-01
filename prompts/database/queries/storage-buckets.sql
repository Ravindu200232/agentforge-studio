-- Storage buckets, with how many objects each holds and how much space they take.
select
  b.id,
  b.name,
  b.public,
  b.file_size_limit,
  b.allowed_mime_types,
  b.created_at,
  b.updated_at,
  count(o.id) as objects,
  coalesce(sum((o.metadata ->> 'size')::bigint), 0) as bytes,
  max(o.created_at) as last_upload
from storage.buckets b
left join storage.objects o on o.bucket_id = b.id
group by b.id
order by b.name;
