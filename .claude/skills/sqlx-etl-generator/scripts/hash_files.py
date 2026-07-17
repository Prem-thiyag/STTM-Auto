#!/usr/bin/env python3
"""
Small utility: sha256 one or more files, print as JSON.

Used by the Artifact Generator specialist to populate metadata/manifest.json's
`inputs` (hash of each of the five source documents) and to independently verify
`generated_files` hashes reported by render_sqlx.py. Kept separate from
render_sqlx.py because manifest assembly needs to hash files render_sqlx.py never
touches (the source documents themselves).

Usage:
    python hash_files.py <file> [<file> ...]

Prints: {"<path>": "sha256:<hex>", ...} to stdout.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python hash_files.py <file> [<file> ...]", file=sys.stderr)
        return 2

    result = {}
    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 2
        result[path.as_posix()] = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
