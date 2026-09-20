# DataPact

DataPact is a Django app that checks recurring data files against rules you define. You set the rules once, such as column types, allowed values, and null constraints. DataPact then checks every new file against them and points to the exact row and value that broke a rule, with a plain-English explanation.

INFO 490, Team 15, Fall 2026.

## Team

Hriday Agarwal, Ashok Chacko, Tejas Jaggi, Connor Slattery

## Where the project is

This repo holds the A1 data model and the A2 work so far.

- Done: the class-based views (Hriday), the HttpResponse view, `.gitignore`, `.env.example`, and the docs (Connor).
- Still to come: the split settings and the render() view (Tejas), and the final templates (Ashok).

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
  data_quality/         models, views, urls, templates, tests
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
