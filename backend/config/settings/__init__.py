"""Settings package.

`DJANGO_ENV` decides which module gets loaded (`dev` or `prod`). The resolution
lives here rather than in `manage.py` because `manage.py`, `wsgi.py` and
`asgi.py` all need the same answer, and all three need `.env` loaded *before*
they can read `DJANGO_ENV`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# config/settings/__init__.py -> config/settings -> config -> backend
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = BACKEND_DIR.parent

_VALID_ENVS = ("dev", "prod")


def load_env() -> None:
    """Load the repo-root `.env` into `os.environ`. Safe to call more than once."""
    load_dotenv(REPO_ROOT / ".env")


def resolve_settings_module() -> str:
    """Return the dotted settings module named by `DJANGO_ENV` (default `dev`)."""
    load_env()
    env = os.environ.get("DJANGO_ENV", "dev").strip().lower()
    if env not in _VALID_ENVS:
        raise ValueError(f"DJANGO_ENV must be one of {_VALID_ENVS}, got {env!r}")
    return f"config.settings.{env}"
