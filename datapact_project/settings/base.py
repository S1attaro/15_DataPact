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
    'django.contrib.sites',
    'data_quality',
    # After data_quality on purpose: Django's app template loader tries apps
    # in this order, so data_quality's own copies of allauth's templates win.
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves everything under STATIC_ROOT. Django's own static handling only
    # works while DEBUG is on, so without this production mode returns 404 for
    # the stylesheet and the site renders unstyled. Must sit directly after
    # SecurityMiddleware. (Section 3, Ashok)
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
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

# Where collectstatic gathers every app's static/ folder. Generated output, so
# it is git-ignored; run `python manage.py collectstatic` before serving in
# production mode. Application CSS and images live in data_quality/static/,
# found automatically by the app-directories finder. (Section 3, Ashok)
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Google sign-in (django-allauth)
# https://docs.allauth.org/en/latest/socialaccount/providers/google.html
#
# The client ID and secret come from the Google Cloud Console and live in .env,
# never in code. Both are optional so the site still starts without them; the
# Google button then simply does not appear.

SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    # Username/password logins (and /admin/) keep working next to Google.
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Where allauth sends the browser after a Google sign-in or a sign-out. Without
# these it falls back to /accounts/profile/, which does not exist.
LOGIN_REDIRECT_URL = 'data_quality:home'
LOGOUT_REDIRECT_URL = 'data_quality:home'

# Google has already verified the address; this also keeps allauth from trying
# to send a confirmation email, which this project has no mail server for.
ACCOUNT_EMAIL_VERIFICATION = 'none'

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '').strip()
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', '').strip()
GOOGLE_OAUTH_CONFIGURED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}
if GOOGLE_OAUTH_CONFIGURED:
    SOCIALACCOUNT_PROVIDERS['google']['APP'] = {
        'client_id': GOOGLE_CLIENT_ID,
        'secret': GOOGLE_CLIENT_SECRET,
        'key': '',
    }
