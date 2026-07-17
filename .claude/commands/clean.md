---
description: Reset the generated workspace (delete output/) without touching source code, input/, or tests.
---

Delete the `output/` directory at the repository root, if it exists, and everything
under it — generated SQLX (`definitions/`), all metadata (`metadata/**`, including
review reports, execution/engine logs, and the validate report), and `bootstrap/`.

Do **not** touch: `input/`, any source code (`engine/`, `.claude/`), `ARCHITECTURE.md`,
or anything under `engine/tests/`. This command only ever removes `output/` — nothing
else in the repository is "generated workspace."

Steps:
1. If `output/` doesn't exist, say so and stop — nothing to do.
2. Otherwise delete `output/` recursively.
3. Confirm deletion and remind the user that `/generate` recreates it from `input/`.
