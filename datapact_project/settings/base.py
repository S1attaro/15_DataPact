"""
Shared Django settings for datapact_project.

Never point DJANGO_SETTINGS_MODULE at this module directly. Choose a mode:

    datapact_project.settings.development   (manage.py default)
    datapact_project.settings.production    (wsgi.py / asgi.py default)

Secrets and host names are read from the environment, normally via the
repository-level .env file. See .env.example for the expected variables.

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# This file is <repo>/datapact_project/settings/base.py, so the repository
# root is three levels up (settings/ -> datapact_project/ -> <repo>).
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load <repo>/.env if present. Variables already set in the real environment
# take precedence over values in the file (python-dotenv default).
load_dotenv(BASE_DIR / '.env')


def require_env(name):
    """Return the value of environment variable `name`, or fail loudly.

    Raises ImproperlyConfigured with instructions when the variable is missing
    or blank, so a missing .env is an obvious setup error rather than a silent
    fallback to an insecure default.
    """
    value = os.getenv(name, '').strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set. Copy .env.example to .env in the project root "
            f"and give {name} a value (see README.md, 'Environment variables')."
        )
    return value


# SECURITY WARNING: keep the secret key used in production secret!
# It is never written in source; it comes from .env / the environment.
SECRET_KEY = require_env('SECRET_KEY')

# DEBUG is intentionally not defined here. development.py sets it to True and
# production.py sets it to False, so neither mode can inherit the wrong value.

# Comma-separated in the environment, e.g. "localhost,127.0.0.1".
# development.py supplies a local fallback; production.py requires a value.
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', '').split(',')
    if host.strip()
]

# No feature calls an external API yet. Read here so that when one does, the
# key already lives in .env rather than in code (A2 Section 1B).
API_KEY = os.getenv('API_KEY', '')


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'data_quality',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'datapact_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'datapact_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
