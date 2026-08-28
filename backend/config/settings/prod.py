"""Production: debug off, rotating file logs, HTTPS security headers."""

from .base import *  # noqa: F403

DEBUG = False

# --- Security headers ---------------------------------------------------
# Caddy terminates TLS and forwards X-Forwarded-Proto. Without this Django sees
# every request as plain HTTP and SECURE_SSL_REDIRECT loops forever.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = [o for o in CORS_ALLOWED_ORIGINS if o.startswith("https://")]

# --- File logging -------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING["handlers"]["app_file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOG_DIR / "app.log",
    "maxBytes": 10 * 1024 * 1024,
    "backupCount": 5,
    "formatter": "standard",
    "encoding": "utf-8",
}
LOGGING["handlers"]["error_file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": LOG_DIR / "error.log",
    "maxBytes": 10 * 1024 * 1024,
    "backupCount": 5,
    "level": "ERROR",
    "formatter": "standard",
    "encoding": "utf-8",
}
LOGGING["root"]["handlers"] = ["console", "app_file", "error_file"]
