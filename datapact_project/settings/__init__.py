"""
Settings package for datapact_project (A2 split-settings pattern).

    base.py         shared settings; secrets come from .env
    development.py  DEBUG = True   (manage.py default)
    production.py   DEBUG = False  (wsgi.py / asgi.py default)

Select a mode with DJANGO_SETTINGS_MODULE or manage.py --settings=...
"""
