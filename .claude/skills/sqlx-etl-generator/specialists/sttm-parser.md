# Specialist: STTM Parser

## Role

Turn the STTM Excel workbook into the normalized Mapping IR defined by
`schemas/sttm.schema.json`. This specialist is split into a deterministic half and
a reasoning half — do not collapse them into one step.

## Step 1 — deterministic (run the script, do not read the workbook yourself)

Run:

```
python scripts/parse_sttm.py <path to STTM workbook> --output <scratch>/sttm.raw.json
```

If it exits non-zero, **stop** — do not open the workbook directly to work around a
parse failure. The script's error message tells you exactly which header or which
row is the problem (see `scripts/parse_sttm.py`'s `REQUIRED_HEADERS` contract and
`references/naming-conventions.md`). Report the exact error back; fixing a
malformed workbook is the user's call, not something to paper over by reading
raw cells yourself. This is the single most important rule for this specialist:
**you never look at the .xlsx file directly.** Every ounce of this specialist's
token-efficiency and determinism guarantee depends on that boundary holding.

A row with **both** Source Table and Source Column blank is not an error — the
script passes it through with `source_table: null, source_column: null`. This is
a legitimate "generated column" mapping (a surrogate key, a UUID, a fixed
default — see Step 2's table below); the script only fails a row where **exactly
one** of the pair is blank, since that's genuinely inconsistent. Every row also
carries a mechanical `duplicate_mapping: true/false` flag (`true` when more than
one row shares the same `target_table`/`target_column`) — see "Duplicate
mappings" below.

## Step 2 — reasoning (classify each row's transformation)

Read `<scratch>/sttm.raw.json`. For every row, classify `transformation_note`
(free text, e.g. "direct copy", "concat first + last", "lookup DIM_X surrogate
key", "always 'ACTIVE'") into exactly one of:

| Value | When |
|---|---|
| `DIRECT` | The note says or clearly implies a 1:1 copy with no logic — a single `source_column`, no `udf_reference` mentioned. Requires a populated `source_table`/`source_column`. |
| `UDF` | The note names or clearly refers to a function listed in `udf.md`. Set `udf_reference` to that function's name as it appears in `udf.md`. Requires a populated `source_table`/`source_column`. |
| `EXPRESSION` | The note describes a self-contained SQL-expressible transformation (concatenation, arithmetic, casting, a `CASE` rule) that does **not** depend on another table's data and has no matching UDF. |
| `CONSTANT` | The note says the target column is always a fixed literal value, independent of any source row. `source_table`/`source_column` are `null` (see `parse_sttm.py`'s raw row — a `CONSTANT` row is exactly the "both blank" case). |
| `LOOKUP` | The note describes deriving the value by looking up another table's already-loaded data (a surrogate key from a dimension, a reference-table value). Requires a populated `source_table`/`source_column` (the natural key correlated against). |
| `GENERATED` | The note describes a value produced with no source at all and no fixed literal either — most commonly a surrogate key ("row number", "sequential ID", "auto-increment"). `source_table`/`source_column` are `null`. The *how* (row-number vs. sequence vs. UUID) is a Mapping Resolver decision, not this specialist's — just classify that the row is sourceless and says "generate a value," and let `transformation_detail` carry the free-text description forward for the Mapping Resolver to read. |
| `DEFAULT` | The note says the column always takes a fixed system/schema default (distinct from `CONSTANT`: a `DEFAULT` note says "whatever the column's own default is," not "always literally X"). `source_table`/`source_column` are `null`. |
| `SEQUENCE` | The note explicitly names a database sequence (`nextval(...)`, "from sequence X"). `source_table`/`source_column` are `null`. |
| `UUID` | The note says the column is a generated UUID/GUID. `source_table`/`source_column` are `null`. |
| `NEEDS_REVIEW` | The note is missing, contradictory, or too ambiguous to confidently place in one of the above — **or** `parse_sttm.py` flagged the row `duplicate_mapping: true` (see "Duplicate mappings" below). **Never guess to avoid this bucket** — an incorrect confident classification is worse than an honest `NEEDS_REVIEW`, because the former ships silently and the latter is caught by Review's check `C5`. |

A row whose raw `source_table`/`source_column` are `null` can only be classified
into one of the five sourceless kinds (`CONSTANT`, `GENERATED`, `DEFAULT`,
`SEQUENCE`, `UUID`) or `NEEDS_REVIEW` — never `DIRECT`, `UDF`, or `LOOKUP`, which
require a real source. Conversely, a row with a populated source can be any kind
except the five sourceless ones. `schemas/sttm.schema.json` enforces this pairing;
treat a schema validation failure here as a sign the classification itself was
wrong, not a schema bug to work around.

### Duplicate mappings

`parse_sttm.py`'s raw output flags every row `duplicate_mapping: true` when more
than one row targets the same `(target_table, target_column)`. When you see this
flag, classify **every row in that group** as `NEEDS_REVIEW` — do not use the
transformation note to decide which one "wins." The workbook itself is
contradictory at that point; adjudicating it is the user's call (via a corrected
workbook and a re-run), not something to resolve by picking the row that looks
more plausible.

For each row, also carry forward `id` (`M###`, assigned in the order rows
appeared in `sttm.raw.json`, per `references/naming-conventions.md`),
`target_table`, `target_column`, `source_table`, `source_column`,
`transformation_detail` (copy `transformation_note` verbatim — this is the audit
trail back to the workbook), `udf_reference`, `notes`.

## Output

Write `metadata/mapping/sttm.json`, validating against `schemas/sttm.schema.json`
(`scripts/validate_schema.py metadata/mapping/sttm.json schemas/sttm.schema.json`).

## Constraints

- Classification is the only reasoning this specialist does. It does not decide
  *how* to write the SQL expression for a mapping — that is the Mapping Resolver's
  job in the next stage, working from this file plus the schema IRs and
  `dependency_graph.json`.
- Do not deduplicate, merge, or drop rows that look redundant — one row in, one
  mapping entry out, always. If the workbook genuinely has a duplicate mapping for
  the same target column, that is a `NEEDS_REVIEW` case (see: "contradictory"),
  not something to silently resolve by picking one.
