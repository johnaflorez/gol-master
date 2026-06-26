"""
Configuración optimizada para la suite de tests.

Se carga automáticamente desde manage.py cuando el comando es `test`.
No debe usarse en producción.
"""

import tempfile
from pathlib import Path

from .settings import *  # noqa: F401,F403


DEBUG = False

# Evita depender de DATABASE_URL real durante tests y acelera la creación de la DB.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# El hasher por defecto de Django es seguro pero costoso; para tests basta uno rápido.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = []

# En tests no se debe tocar S3/Supabase ni /tmp/media real.
USE_S3_MEDIA = False
MEDIA_ROOT = Path(tempfile.gettempdir()) / "gol_master_test_media"
MEDIA_URL = "/media/"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Evita llamadas lentas accidentales a proveedores externos durante tests.
FOOTBALL_DATA_TIMEOUT = 1
FOOTBALL_DATA_COMPETITION_CODE = "WC"
FOOTBALL_DATA_SEASON = 2026
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Silencia trazas esperadas en tests que fuerzan errores de storage.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "loggers": {
        "users.views": {
            "handlers": ["null"],
            "level": "CRITICAL",
            "propagate": False,
        },
    },
}
