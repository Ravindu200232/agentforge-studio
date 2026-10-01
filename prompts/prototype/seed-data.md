# Sample database rows

Write realistic sample rows for every table below, as if this product has been in
real use for a while. These rows become the actual starting data of a working local
database inside the prototype: every page that lists, shows, edits or deletes a
record reads and writes exactly these rows, so they must be internally consistent —
a foreign key value must be an `id` that really exists in the table it refers to —
and varied enough to show what a real screen needs: recent and older records,
more than one status where the table has one, more than one owner where it has
an owner.

Give each table 6 to 12 rows. Give every row a short, stable `id` string (for
example `ord-1`, `ord-2`). Use the exact field names given for each table; invent
no extra field and omit none that is listed.

Return JSON only, nothing before or after it:

```json
{"tables": {"<table name>": [{"id": "...", "...field...": "..."}]}}
```

## The product

{{product}}

## Tables

{{tables}}
