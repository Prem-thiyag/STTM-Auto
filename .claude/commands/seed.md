---
description: Reset and prepare the three PostgreSQL databases (source_db, intermediate_db, target_db) this project's pipeline expects. Does not load any data.
---

Prepare PostgreSQL for a pipeline run. This command only resets/prepares the three
databases the generated pipeline always expects to exist — `source_db`,
`intermediate_db`, `target_db` — on the same PostgreSQL instance. **It never inserts
any row-level data**, seed or otherwise: this project's generator never fabricates
business data (see `ARCHITECTURE.md` §5/§9), and any reference dataset is loaded
manually, outside this command.

Run:

```
python -m engine.dbadmin seed
```

This connects using `engine.postgres.resolve_connection_config` (an `.mcp.json`
Postgres entry, or `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` env vars — never a
hardcoded credential), then for each of `source_db`, `intermediate_db`, `target_db`:
terminates any other sessions on it, drops it if it exists, and creates it fresh and
empty.

Report back exactly what the command printed — which databases were reset — and
remind the user that table structure comes from `/execute` (which runs the
project's bootstrap SQL) after `/generate` has produced it, and that any reference
dataset must be loaded into `source_db` manually before `/execute`.

Do not run this against a database that has active work you haven't confirmed is
safe to discard — check with the user first if anything about the current database
state looks unexpected (e.g. active sessions, unfamiliar tables already present).
