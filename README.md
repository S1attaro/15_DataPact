# DataPact

DataPact is a Django app that checks recurring data files against rules you define. You set the rules once, such as column types, allowed values, and null constraints. DataPact then checks every new file against them and points to the exact row and value that broke a rule, with a plain-English explanation.

INFO 490, Team 15, Fall 2026.

## Team

Hriday Agarwal, Ashok Chacko, Tejas Jaggi, Connor Slattery

## Where the project is

This repo holds the A1 data model and the A2 work so far.

- Done: the class-based views (Hriday), the HttpResponse view, `.gitignore`, `.env.example`, and the docs (Connor), and the templates (Ashok).
- Still to come: the split settings and the render() view (Tejas).

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

Fill in your own values. Do not commit `.env`. Git ignores it. The current `settings.py` does not read it yet. That changes with the split settings.

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
| `SECRET_KEY` | Django secret key. Make your own for `.env`. |
| `ALLOWED_HOSTS` | Comma-separated hosts. Use `localhost,127.0.0.1` locally. |
| `API_KEY` | A dummy value for now. There is no external API yet. |

To make a new secret key:

```
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

## Running

```
python manage.py runserver
```

Then open http://127.0.0.1:8000/datasets/. Production settings are not set up yet and will be added with the split settings.

## Pages

| URL | View | Kind |
| --- | --- | --- |
| `/datasets/manual/` | `dataset_manual` | Function-based, HttpResponse |
| `/datasets/render/` | not written yet | Function-based, render() |
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

Run these before you open a pull request.

## Project layout

```
15_DataPact/
  README.md
  manage.py
  requirements.txt
  .env.example          placeholder values, safe to commit
  .gitignore
  db.sqlite3            demo database
  datapact_project/     settings and root URLs
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
