"""
Enables `python -m engine [project_root]` as the primary CLI entry point.

Deliberately a separate file from executor.py: __init__.py imports Engine
(and other public names) from engine.executor for the package's public API,
so running `python -m engine.executor` directly re-imports that same module
under the `__main__` identity and triggers a (harmless but noisy) "module
found in sys.modules" warning. A dedicated __main__.py sidesteps that
entirely -- it is never imported by __init__.py, only executed by `-m`.
"""

import sys

from engine.executor import main

if __name__ == "__main__":
    sys.exit(main())
