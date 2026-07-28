"""The mapped models must import in any order.

`app.audit.models` imports `app.models.base`, so a registry living in
`app.models.__init__` would import the feature models while they are importing
it — and the app would only start if something happened to import the package
first. `app.models.registry` exists to keep that cycle impossible; this is the
regression guard.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "module",
    ["app.audit.models", "app.users.models", "app.models.registry", "app.core.database"],
)
def test_a_model_module_imports_on_its_own(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=SERVER_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
