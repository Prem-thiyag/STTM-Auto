# Bootstrap — retail-analytics-etl

Sets up the three PostgreSQL databases this project's generated pipeline expects:
`source_db` (source), `intermediate_db` (staging), and
`target_db` (target). Every script here is plain SQL, run manually — no
script in this folder is ever executed automatically by any plan in this skill.
That's deliberate: see the parent project's `metadata/` for the pipeline itself,
which follows the same manual-execution rule.

## Run order

```
1. db/01_init/01_create_schemas.sql                       (run against each of the 3 databases)
2. db/02_source/ddl_source_tables.sql                      (run against source_db)
3. db/04_target/ddl_target_tables.sql                      (run against target_db)
4. db/01_init/02_create_fdw_intermediate_to_source.sql     (run against intermediate_db)
5. db/03_intermediate/init_staging_schema.sql               (run against intermediate_db)
6. db/03_intermediate/create_udfs.sql                        (run against intermediate_db)
7. (after step 2's tables exist) db/02_source/seed_source_data.sql -- fill in the
   TODOs first; no sample data is fabricated by this generator (see project root
   docs/ASSUMPTIONS.md)
8. (after the pipeline's Generate has run at least once, so staging tables exist)
   db/01_init/03_create_fdw_target_to_intermediate.sql       (run against target_db)
```

Steps 4 and 8 need connection details for the *other* database, which this
generator cannot know — supply them as psql variables, for example:

```
psql -d intermediate_db \
  -v remote_host=<host> -v remote_port=5432 \
  -v remote_user=<user> -v remote_password=<password> \
  -f db/01_init/02_create_fdw_intermediate_to_source.sql
```

## Reset

`reset/reset_source.sql` and `reset/reset_target.sql` truncate every table each
schema declares, in dependency order. Also manual — run them yourself when you
want a clean environment; nothing in this skill runs them for you.

## Tracked objects

`manifest.json` in this folder lists every database object these scripts create,
for reference. It is a separate file from the parent project's
`metadata/cleanup/cleanup_manifest.json` — that one tracks the pipeline's own
per-run staging/target objects, not this environment scaffolding. Tearing down
one should never be confused with tearing down the other.

## Tables in this project

- CUSTOMER
- CUSTOMER_ORDER
- DIM_CUSTOMER
- FACT_ORDER
