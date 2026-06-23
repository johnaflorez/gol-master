"""
Django settings for config project.
"""

import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-8i66z6vc1(72i$09$v^6nou$^ty95sarr75x1%#9q6&^a)k-y8')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

def _split_env_list(var_name, default=""):
    raw = os.environ.get(var_name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]

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
    'corsheaders'
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
CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL', '')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')
CLOUDINARY_MEDIA_FOLDER = os.environ.get('CLOUDINARY_MEDIA_FOLDER', 'gol_master')
CLOUDINARY_STORAGE_ENABLED = (
    os.environ.get('CLOUDINARY_STORAGE_ENABLED', '').lower() == 'true'
    or bool(CLOUDINARY_URL)
    or bool(CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET)
)
_default_media_root = BASE_DIR / 'media'
if os.environ.get('RENDER', '').lower() == 'true':
    _default_media_root = Path('/tmp/media')
MEDIA_ROOT = Path(os.environ.get('MEDIA_ROOT', str(_default_media_root)))


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

if CLOUDINARY_STORAGE_ENABLED:
    STORAGES = {
        'default': {
            'BACKEND': 'users.storage.CloudinaryMediaStorage',
        },
        'staticfiles': {
            'BACKEND': STATICFILES_STORAGE,
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

# API-Football / API-SPORTS integration
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
API_FOOTBALL_BASE_URL = os.environ.get('API_FOOTBALL_BASE_URL', 'https://v3.football.api-sports.io')
API_FOOTBALL_TIMEOUT = int(os.environ.get('API_FOOTBALL_TIMEOUT', '15'))

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
