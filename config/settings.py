"""
Django settings for config project.
"""

import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-8i66z6vc1(72i$09$v^6nou$^ty95sarr75x1%#9q6&^a)k-y8')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

def _split_env_list(var_name, default=""):
    raw = os.environ.get(var_name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


def _env_bool(var_name, default=False):
    raw = os.environ.get(var_name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}

ALLOWED_HOSTS = _split_env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')

# Application definition
LOCAL_APPS = [
    'users',
    'teams',
    'matches',
    'predictions',
    'rankings',
    'core',
    'stats'
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'corsheaders',
    'storages',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
] + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # <- whitenoise, justo despues de security
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.final_match_announcements',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# En produccion Render define DATABASE_URL automaticamente
DATABASE_URL_ENV = os.environ.get('DATABASE_URL')
if DATABASE_URL_ENV:
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL_ENV, conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
_default_media_root = BASE_DIR / 'media'
if os.environ.get('RENDER', '').lower() == 'true':
    _default_media_root = Path('/tmp/media')
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', str(_default_media_root)))
USE_S3_MEDIA = _env_bool('USE_S3_MEDIA')


def _ensure_writable_media_root(path):
    path.mkdir(parents=True, exist_ok=True)
    probe = path / '.write-test'
    probe.write_text('ok', encoding='utf-8')
    probe.unlink(missing_ok=True)


try:
    _ensure_writable_media_root(MEDIA_ROOT)
except OSError:
    if os.environ.get('RENDER', '').lower() == 'true':
        MEDIA_ROOT = Path('/tmp/media')
        try:
            _ensure_writable_media_root(MEDIA_ROOT)
        except OSError:
            pass


if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', '')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_SIGNATURE_VERSION = os.environ.get('AWS_S3_SIGNATURE_VERSION', 's3v4')
    AWS_S3_ADDRESSING_STYLE = os.environ.get('AWS_S3_ADDRESSING_STYLE', 'path')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '')
    AWS_S3_URL_PROTOCOL = os.environ.get('AWS_S3_URL_PROTOCOL', 'https:')
    AWS_QUERYSTRING_AUTH = _env_bool('AWS_QUERYSTRING_AUTH', False)
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': os.environ.get('AWS_S3_CACHE_CONTROL', 'max-age=86400'),
    }

    MEDIA_URL = os.environ.get('MEDIA_URL', MEDIA_URL)
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }


# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ]
}

# CORS
CORS_ALLOWED_ORIGINS = _split_env_list('CORS_ALLOWED_ORIGINS', 'http://localhost:5173')
CORS_ALLOW_CREDENTIALS = True

# football-data.org integration (marcadores/resultados; no incluye eventos)
FOOTBALL_DATA_TOKEN = os.environ.get('FOOTBALL_DATA_TOKEN', '54825cc619d144d0977380aaa2fd67a6')
FOOTBALL_DATA_BASE_URL = os.environ.get('FOOTBALL_DATA_BASE_URL', 'https://api.football-data.org/v4')
FOOTBALL_DATA_TIMEOUT = int(os.environ.get('FOOTBALL_DATA_TIMEOUT', '15'))
FOOTBALL_DATA_COMPETITION_CODE = os.environ.get('FOOTBALL_DATA_COMPETITION_CODE', 'WC')
FOOTBALL_DATA_SEASON = int(os.environ.get('FOOTBALL_DATA_SEASON', '2026'))
FOOTBALL_DATA_SCORERS_LIMIT = int(os.environ.get('FOOTBALL_DATA_SCORERS_LIMIT', '500'))

# Celery / Celery Beat
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get('CELERY_TASK_SOFT_TIME_LIMIT', '240'))
CELERY_TASK_TIME_LIMIT = int(os.environ.get('CELERY_TASK_TIME_LIMIT', '300'))
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_BEAT_SCHEDULE = {
    'sync-live-matches-every-5-minutes': {
        'task': 'matches.tasks.sync_live_matches',
        'schedule': crontab(minute='*/5'),
        'options': {
            'expires': int(os.environ.get('CELERY_SYNC_LIVE_EXPIRES', '240')),
        },
    },
}

# Accept HTTPS form posts from Render/custom domains when DEBUG=False
CSRF_TRUSTED_ORIGINS = _split_env_list(
    'CSRF_TRUSTED_ORIGINS',
    'https://localhost,https://127.0.0.1'
)

# Auth redirects
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

# Seguridad en produccion
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
