# ABOUTME: Loads .env from the repo root into a dict for the other scripts.
# ABOUTME: No external deps; fails loud if a required key is missing.
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    env: dict[str, str] = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip())
    return env


def require(env: dict[str, str], key: str) -> str:
    value = env.get(key, "")
    if not value:
        sys.exit(f"FATAL: {key} not set in environment or {REPO_ROOT / '.env'}")
    return value
