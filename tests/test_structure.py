import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_documented_entrypoints_and_project_structure_exist():
    for relative in (
        "backend/app/main.py",
        "backend/app/domain/models.py",
        "backend/app/domain/interfaces.py",
        "frontend/app.py",
        "workers/README.md",
        "scripts/setup.sh",
        "scripts/run_backend.sh",
        "scripts/run_frontend.sh",
        "README.md",
        "AGENTS.md",
        "docs/architecture.md",
        "docs/business-rules.md",
        ".env.example",
        "uv.lock",
    ):
        assert (ROOT / relative).is_file(), relative


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        "private-token.txt",
        "credentials.json",
        ".streamlit/secrets.toml",
        "documents/hospital.pdf",
        "budget.xlsx",
        "confidential/export.csv",
        "patients/record.json",
        "pacientes/registro.json",
        "uploads/image.png",
    ],
)
def test_confidential_paths_are_ignored(path):
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", path], cwd=ROOT, check=False
    )
    assert result.returncode == 0, path


def test_safe_environment_example_can_be_versioned():
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", ".env.example"], cwd=ROOT, check=False
    )
    assert result.returncode == 1
