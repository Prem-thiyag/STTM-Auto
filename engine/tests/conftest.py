from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def real_output_project() -> Path:
    """The actual generated project built from input/ during this session --
    real SQLX, real buildspecs, real execution plan. Using real generator
    output (not a synthetic fixture) is deliberate: it's the same standard
    the sqlx-etl-generator skill itself holds to (see its docs/examples/ and
    scripts/smoke_test.py) -- prove the engine against something the
    generator actually produced, not an idealized stand-in."""
    path = REPO_ROOT / "output"
    assert path.exists(), f"expected a real generated project at {path}"
    return path
