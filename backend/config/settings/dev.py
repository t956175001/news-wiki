"""Local development: debug on, logs to the console only."""

from .base import *  # noqa: F403

DEBUG = True

# Vite dev server runs on a different origin, so the browser needs both of these.
CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# The manifest storage requires `collectstatic` to have run; not worth it locally.
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"}

# WhiteNoise warns on every request when STATIC_ROOT is missing, which it always
# is locally until someone runs collectstatic.
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
