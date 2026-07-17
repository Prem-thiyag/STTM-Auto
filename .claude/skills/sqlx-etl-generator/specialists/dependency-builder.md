# Specialist: Dependency Builder

## Role

Build the table/stage-level execution DAG from the two schema IRs and the mapping
IR, and produce a strict topological order. This is the last specialist allowed to
read `sttm.json` and the schema IRs directly — the Mapping Resolver reads them too,
but every specialist after that (SQLX Generator, Artifact Generator) only ever
reads this specialist's output plus the buildspecs.

## Input

- `metadata/schema/source_schema.json`
- `metadata/schema/target_schema.json`
- `metadata/mapping/sttm.json`

## Output

`metadata/dependency/dependency_graph.json`, validating against
`schemas/dependency_graph.schema.json`.

## Process

1. **Nodes.** For every target table named in `sttm.json`'s mappings, create three
   nodes: `<TABLE>.read`, `<TABLE>.process`, `<TABLE>.write`.
2. **Intra-table edges.** `<TABLE>.read -> <TABLE>.process -> <TABLE>.write` for
   every table, always — this ordering is structural, not something to infer from
   the mappings.
3. **Cross-table edges.** For every mapping row whose `transformation_note` (or, if
   you're running after the STTM Parser's classification, whose `transformation`
   value) implies a `LOOKUP` against another *target* table's already-loaded data,
   add an edge `<OTHER_TABLE>.write -> <THIS_TABLE>.process` with a `reason` string
   naming the column and what it looks up (e.g. `"FK lookup: <column> references
   <other table>"`). Only add an edge when the lookup target is a *target* table
   this project is also generating — a lookup against a source table doesn't
   create a cross-table ordering constraint (it's resolved directly in `read.sqlx`
   via the source FDW connection, see `references/sqlx-syntax-guide.md`).
4. **Topological sort.** Compute `execution_order` over all nodes (Kahn's algorithm
   or equivalent). Every node must appear exactly once.
5. **Cycle check — mandatory, not optional.** If step 4 cannot place every node
   (a cycle exists), **do not write `dependency_graph.json` at all** and abort the
   entire Generate run with a clear error naming the tables involved in the cycle.
   Per ADR-001: a cycle here means the STTM or schema documents describe an
   impossible load order, and Generate must produce no partial output rather than
   guess an order that could violate a foreign key at execution time.

## Constraints

- This specialist reasons about *ordering*, never about *transformation logic*.
  Do not compute SQL expressions, resolve UDFs, or touch anything that belongs in
  a buildspec — that's the Mapping Resolver's job, immediately after this one.
- Every edge needs a `reason`. An edge without one is not traceable, and a future
  reviewer (human or Review plan) has no way to sanity-check it.
