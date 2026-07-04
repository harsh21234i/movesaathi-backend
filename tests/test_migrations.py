from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_alembic_upgrade_head_runs_on_sqlite() -> None:
    repo_root = Path(os.path.dirname(os.path.dirname(__file__)))
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "migration-smoke.db"
        env = os.environ.copy()
        env.update(
            {
                "APP_ENV": "test",
                "SECRET_KEY": "x" * 32,
                "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
                "REDIS_URL": "redis://localhost:6379/0",
                "AUTO_CREATE_TABLES": "false",
                "BACKEND_CORS_ORIGINS": json.dumps(["http://localhost:5173"]),
            }
        )

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        assert result.returncode == 0
        assert db_path.exists()
