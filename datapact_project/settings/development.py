"""
Development settings: DEBUG on, local hosts allowed by default.

Used automatically by manage.py. Override with DJANGO_SETTINGS_MODULE or
    python manage.py <command> --settings=datapact_project.settings.development
"""

import os

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Fall back to the local machine when .env does not name any hosts.
if not ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Optional, development only: point Django at a different SQLite file so the
# committed demo database (db.sqlite3) is never touched by experiments or
# empty-state screenshots. Relative names resolve from the repository root;
# leave DATABASE_NAME unset to use db.sqlite3. production.py ignores this.
_database_name = os.getenv('DATABASE_NAME', '').strip()
if _database_name:
    # Copy rather than mutate, so base.py's dict (shared with production.py
    # when both are imported in one process, e.g. the test suite) is untouched.
    DATABASES = {**DATABASES, 'default': {**DATABASES['default']}}  # noqa: F405
    DATABASES['default']['NAME'] = (BASE_DIR / _database_name).resolve()  # noqa: F405
