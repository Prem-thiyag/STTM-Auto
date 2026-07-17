# User Defined Functions

## fn_full_name

Concatenates a first and last name into a single display name, trimming
whitespace and collapsing a missing last name gracefully.

```sql
CREATE OR REPLACE FUNCTION fn_full_name(p_first_name text, p_last_name text)
RETURNS text AS $$
    SELECT trim(both ' ' from coalesce(p_first_name, '') || ' ' || coalesce(p_last_name, ''));
$$ LANGUAGE sql IMMUTABLE;
```
