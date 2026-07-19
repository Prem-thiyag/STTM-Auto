---
description: One-time (or repeat-safe) local dev environment bootstrap -- creates ./venv, installs every Python dependency into it, and installs envmcp if Node is available.
---

Run exactly one command, nothing else:

```
python tool/setup_env.py
```

Relay its output directly — it already prints each step (venv creation or
reuse, each `pip install` it ran, whether it found Node and installed
`envmcp`, and the final activate-the-venv instruction) rather than
re-deriving or re-describing what it did.

If it fails, report the exact command that failed and its error — don't
guess at a fix or silently retry. If Python itself isn't on `PATH`, or the
venv creation step fails, that's an environment problem for the user to
resolve (missing Python install, permissions, etc.), not something to work
around from inside this command.
