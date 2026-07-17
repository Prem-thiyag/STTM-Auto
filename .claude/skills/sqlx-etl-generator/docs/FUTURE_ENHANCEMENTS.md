# Future Enhancements

Directions ADR-001 §11 names explicitly, restated here as concrete next steps
rather than architectural rationale (see the ADR for the "why").

- **Sample data as a declared input.** Today `bootstrap/db/02_source/seed_source_data.sql`
  is a stub by design (`docs/ASSUMPTIONS.md`). Adding a real sixth input type
  (CSV or SQL) would let it become real, still deterministically — see
  `docs/EXTENSION_POINTS.md` "Adding a sixth input type."
- **Incremental / SCD2 load strategies.** `buildspec.schema.json` already
  reserves the enum values; only the templates and renderer branch are
  missing. See `docs/EXTENSION_POINTS.md` "Adding a new `load_strategy`."
- **Additional SQL dialects.** The buildspec IR is already dialect-agnostic;
  this is purely a new `templates/<dialect>/` tree plus a renderer flag. See
  `docs/EXTENSION_POINTS.md` "Adding a new SQL dialect."
- **Automating `Execute`.** Today it prints one command and waits for a human
  to confirm. An "auto" mode could feed `execution_plan.json` commands
  straight to a Postgres MCP connection programmatically and write the same
  `execution_log.json` shape — no change to any reasoning specialist required.
  This is the direct payoff of having kept `Execute` metadata-driven from the
  start rather than baking manual confirmation into its logic ad hoc.
- **Automating `Review`'s `schema_cross_check`.** Currently optional and
  degrades to `WARN` when no read-only Postgres MCP connection is available
  (see `plans/review.md`). As MCP connectivity becomes more reliably available
  in a given environment, this check could be made mandatory for that
  environment — a configuration change to how `review_spec.json`'s `C6`-type
  checks are emitted by the Artifact Generator, not an architecture change.
- **Multi-source-database targets.** `buildspec.schema.json`'s `source_tables`
  already supports multiple `(database, table)` pairs per target table
  (exercised by any table needing a join across source tables); nothing
  additional is needed here, but it's untested beyond the two-table,
  single-source-table-per-target fixture in `docs/examples/` — worth adding a
  second fixture exercising a genuine multi-database join before relying on
  it in production.
- **Column-level `nullable` propagation into buildspecs.** Schema IR carries
  `nullable` per column; buildspecs currently don't (see
  `schemas/buildspec.schema.json`). If Review grows a data-quality check for
  "no NULLs landed in a non-nullable target column," this would need to be
  added to `columns[]` in the buildspec schema and populated by the Mapping
  Resolver — a small, additive schema change, not a redesign.
