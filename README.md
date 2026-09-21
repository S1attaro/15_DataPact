# DataPact

DataPact is a Django app that checks recurring data files against rules you define. You set the rules once, such as column types, allowed values, and null constraints. DataPact then checks every new file against them and points to the exact row and value that broke a rule, with a plain-English explanation.

INFO 490, Team 15, Fall 2026.

## Team

Hriday Agarwal, Ashok Chacko, Tejas Jaggi, Connor Slattery

## Where the project is

This repo holds the A1 data model and the A2 work so far.

- Done: the class-based views (Hriday), the HttpResponse view, `.gitignore`, `.env.example`, and the docs (Connor), the templates (Ashok), the split settings, the render() view, and the tests (Tejas).
- Still to come: later assignments build on this base.

## Setup

These steps are for Windows PowerShell. You need Python 3 and Git.

1. Clone the repo.

```
git clone https://github.com/S1attaro/15_DataPact.git
cd 15_DataPact
```

2. Create and activate a virtual environment.

```
python -m venv venv
venv\Scripts\Activate.ps1
```

If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process Bypass` and try again.

3. Install the packages.

```
pip install -r requirements.txt
```

4. Make your own `.env` file.

```
Copy-Item .env.example .env
```

Fill in your own values. Do not commit `.env`. Git ignores it. Settings read `.env` on startup; without a `SECRET_KEY` every `manage.py` command stops with a message telling you to create the file.

5. The repo already includes `db.sqlite3` with demo data, so you can skip this step. To reset the database, run:

```
python manage.py migrate
python manage.py seed_demo
```

`seed_demo` clears the app tables before it loads the demo data.

## Environment variables

`.env.example` lists these. The values in it are placeholders.

| Name | Purpose |
| --- | --- |
| `SECRET_KEY` | Django secret key. Required. Make your own for `.env`. Production mode refuses keys that start with `django-insecure-`. |
| `ALLOWED_HOSTS` | Comma-separated hosts. Use `localhost,127.0.0.1` locally. |
| `API_KEY` | A dummy value for now. There is no external API yet. |
| `DATABASE_NAME` | Optional, development only. Set it to `db.local.sqlite3` to work against a throwaway database (ignored by Git) instead of the demo `db.sqlite3`. Run `python manage.py migrate` once after setting it. |

To make a new secret key:

```
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

## Running

```
python manage.py runserver
```

Then open http://127.0.0.1:8000/datasets/.

`manage.py` uses the development settings (`DEBUG = True`). To run with the production settings (`DEBUG = False`, `ALLOWED_HOSTS` required):

```
python manage.py runserver --settings=datapact_project.settings.production
```

`wsgi.py` and `asgi.py` default to the production settings. `DJANGO_SETTINGS_MODULE` overrides either default. Static files (admin CSS) are not served in production mode by `runserver`; that is normal.

## Pages

| URL | View | Kind |
| --- | --- | --- |
| `/datasets/manual/` | `dataset_manual` | Function-based, HttpResponse |
| `/datasets/render/` | `dataset_render` | Function-based, render() |
| `/datasets/overview/` | `DatasetOverviewView` | Class-based, View |
| `/datasets/` | `DatasetListView` | Class-based, ListView |
| `/datasets/<id>/` | `DatasetDetailView` | Class-based, DetailView |
| `/admin/` | Django admin | Built in |

## Templates

Every page extends one base template, so the navigation, stylesheet, page
header and footer are written once.

```
data_quality/templates/data_quality/
  base.html                    site shell: <head>, CSS, top nav, page header, footer
  dataset_list.html            wireframe screen 1, the dataset registry
  dataset_detail.html          wireframe screen 2, one dataset and its contracts
  dataset_overview.html        contract coverage per dataset
  includes/
    _empty_state.html          the shared "nothing here yet" block
    _status_badge.html         the shared DRAFT / ACTIVE / RETIRED pill
```

Blocks a page can fill in: `title`, `extra_head`, `breadcrumbs`, `page_title`,
`page_subtitle`, `page_actions`, `content`.

`dataset_list.html` is written against a single context variable, `datasets`,
so it does not depend on which kind of view rendered it. Any view can reuse it:

```python
return render(request, "data_quality/dataset_list.html", {
    "datasets": Dataset.objects.select_related("owner"),
    "view_label": "Function-based view - render()",
})
```

`view_label` is optional. It fills the small caption under the page title that
names the view kind, and falls back to naming the `ListView` when it is absent.

Each list has an empty state written as `{% for %} ... {% empty %}`, not as a
separate `{% if %}` check. `data_quality/tests.py` asserts on the empty-state
wording, so reword one and fix its test in the same commit.

The CSS is inline in `base.html` rather than in `static/` on purpose:
`runserver` stops serving static files once `DEBUG = False`, so an external
stylesheet would load in dev and 404 in prod. Inline CSS looks the same in both
modes with no `collectstatic` step.

## Tests

```
python manage.py test data_quality
```

34 tests: the three class-based views, the templates, the render() view, and the settings split. Run them before you open a pull request.

## Project layout

```
15_DataPact/
  README.md
  manage.py
  requirements.txt
  .env.example          placeholder values, safe to commit
  .gitignore
  db.sqlite3            demo database
  datapact_project/     root URLs, wsgi, asgi
    settings/           base.py (shared), development.py, production.py
  data_quality/         models, views, urls, tests
    templates/
      data_quality/     base.html, page templates, includes/ partials
  docs/
    notes/              notes.txt, with weekly updates from each teammate
    wireframes/v1/      wireframes PDF
    branching_strategy/ how we use branches and pull requests
    screenshots/        A2 browser screenshots
```

## Git workflow

- No one commits directly to `main`.
- Each task gets its own branch, named `name/task`, like `connor/env-example`.
- Every change reaches `main` through a pull request, merged with a merge commit.
- Pull `main` before you start a new branch.

More detail is in `docs/branching_strategy/branching_strategy.txt`.
