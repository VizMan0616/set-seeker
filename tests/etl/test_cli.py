"""CLI end-to-end: `python -m app.etl --pack mhfu` against a scratch database,
including Alembic migrations and the validation gate."""

import subprocess
import sys

from tests.etl.conftest import REPO_ROOT


def test_cli_end_to_end(tmp_path):
    db_path = tmp_path / "cli.db"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.etl",
            "--pack",
            "mhfu",
            "--database-url",
            f"sqlite:///{db_path}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "[etl]   armor_pieces: 2080" in proc.stdout
    assert "[etl]   decorations: 168" in proc.stdout
    assert "[gate] all checks passed" in proc.stdout

    # Idempotent at the CLI level too: a second run against the same DB passes.
    again = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.etl",
            "--pack",
            "mhfu",
            "--database-url",
            f"sqlite:///{db_path}",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert again.returncode == 0, again.stderr
    assert "[gate] all checks passed" in again.stdout
