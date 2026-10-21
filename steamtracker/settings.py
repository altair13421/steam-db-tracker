"""Django settings for the Steam Tracker project.

Design choices:
  - Single-file settings, no env-specific splits (small project).
  - Environment variables drive every tunable; sensible defaults so
    the project runs out-of-the-box with `python manage.py runserver`.
  - SQLite by default, but DATABASE_URL is honored (Postgres-ready).
  - Charts are saved as PNGs under MEDIA_ROOT and served via MEDIA_URL.
"""
from __future__ import annotations

import os
from pathlib import Path

# Build paths inside the project.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core Django -----------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-insecure-secret-change-me-in-production-please",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get(
        "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
    ).split(",") if h.strip()
]

# --- Apps ------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "whitenoise.runserver_nostatic",  # serve static in dev too
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "steamtracker.urls"

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

WSGI_APPLICATION = "steamtracker.wsgi.application"
ASGI_APPLICATION = "steamtracker.asgi.application"

# --- Database --------------------------------------------------------------

# Default: SQLite at BASE_DIR/data/steam.sqlite3 (Docker-friendly).
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Only honor DATABASE_URL if it looks like a Postgres/MySQL connection —
# ignoring any unrelated file:// scheme that might leak from the host env.
if DATABASE_URL and (
    DATABASE_URL.startswith("postgres")
    or DATABASE_URL.startswith("mysql")
    or DATABASE_URL.startswith("mssql")
):
    import dj_database_url
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(DATA_DIR / "steam.sqlite3"),
        }
    }

# --- Auth / security -------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static + Media --------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "tracker" / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", str(BASE_DIR / "media")))
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

# --- Defaults passed down to the tracker service ---------------------------

STEAM_CC = os.environ.get("STEAM_CC", "us")
STEAM_LANG = os.environ.get("STEAM_LANG", "english")
STEAM_THROTTLE_SECONDS = int(os.environ.get("STEAM_THROTTLE_SECONDS", "4"))
SCHEDULE_INTERVAL = os.environ.get("SCHEDULE_INTERVAL", "12 hours")

CHART_DIR = MEDIA_ROOT / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Logging — both console and a rotating file.
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOG_DIR / "steam_tracker.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
    },
    "root": {"level": "INFO", "handlers": ["console", "file"]},
    "loggers": {
        "tracker": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
    },
}
