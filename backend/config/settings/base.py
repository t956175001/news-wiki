"""Shared settings. Everything environment-specific is read from `.env`.

See `docs/ARCHITECTURE.md` section 7 for the authoritative list of variables.
"""

import os

import dj_database_url

from . import BACKEND_DIR, REPO_ROOT, load_env

load_env()

BASE_DIR = BACKEND_DIR


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is missing. Copy .env.example to .env and fill it in."
        )
    return value


def _csv(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Core ---------------------------------------------------------------

SECRET_KEY = _require("SECRET_KEY")

DEBUG = False

ALLOWED_HOSTS = _csv("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    # Project apps
    "apps.common",
    "apps.common.prompts",
    "apps.ingest",
    "apps.wiki",
    "apps.brief",
    "apps.ops",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database -----------------------------------------------------------

DATABASES = {
    "default": dj_database_url.parse(
        _require("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N / TZ ----------------------------------------------------------

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# --- Static / media -----------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF ----------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.common.drf_exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "news-wiki API",
    "DESCRIPTION": "每日 AI 资讯的可溯源结构化维基。",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
}

# --- CORS ---------------------------------------------------------------

# Empty when frontend and backend are served from the same origin (Caddy reverse proxy).
CORS_ALLOWED_ORIGINS = _csv("CORS_ALLOWED_ORIGINS")

# --- Logging ------------------------------------------------------------

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
# Relative LOG_DIR is resolved against the repo root, so the documented default
# `backend/logs` means the same thing whichever directory you run from.
LOG_DIR = (REPO_ROOT / os.environ.get("LOG_DIR", "backend/logs").strip()).resolve()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

# --- LLM (GLM only) -----------------------------------------------------

GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_MODEL = os.environ.get("GLM_MODEL", "glm-4.7")
GLM_BASE_URL = os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")

LLM_RATE_LIMIT_RPM = int(os.environ.get("LLM_RATE_LIMIT_RPM", "60"))
LLM_DAILY_BUDGET_CNY = float(os.environ.get("LLM_DAILY_BUDGET_CNY", "5.0"))

# --- Extraction pipeline ------------------------------------------------

EXTRACT_BATCH_SIZE = int(os.environ.get("EXTRACT_BATCH_SIZE", "5"))
EXTRACT_CONTENT_LIMIT = int(os.environ.get("EXTRACT_CONTENT_LIMIT", "4000"))

# --- Demo guard rails ---------------------------------------------------

DEMO_MODE = _bool("DEMO_MODE", True)
DEMO_WRITE_RATE = os.environ.get("DEMO_WRITE_RATE", "3/day")

# --- Cron ---------------------------------------------------------------

CRON_TOKEN = os.environ.get("CRON_TOKEN", "")

# --- Outbound proxy (optional; empty means direct connection) -----------

HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
HTTPS_PROXY = os.environ.get("HTTPS_PROXY", "")
