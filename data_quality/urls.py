from django.urls import path

from . import views

app_name = "data_quality"

urlpatterns = [
    # --- Home and navigation (Section 1, Tejas) ---
    path("", views.home, name="home"),

    # --- CBVs (this section owned by Hriday) ---
    path("datasets/overview/", views.DatasetOverviewView.as_view(), name="dataset-cbv-base"),
    path("datasets/", views.DatasetListView.as_view(), name="dataset-list"),
    path("datasets/<int:pk>/", views.DatasetDetailView.as_view(), name="dataset-detail"),

    # --- FBVs ---
    path("datasets/manual/", views.dataset_manual, name="dataset-manual"),
    path("datasets/render/", views.dataset_render, name="dataset-render"),

    # --- Section 2: ORM search + aggregations (Hriday) ---
    path("contracts/search/", views.ContractSearchView.as_view(), name="contract-search"),

    # --- Section 5: forms and user input (Hriday) ---
    path("datasets/manage/", views.DatasetManageView.as_view(), name="dataset-manage"),

    # --- Section 4: quality analytics (Tejas) ---
    path("quality/", views.quality_history, name="quality-history"),
    path(
        "quality/run-outcomes.png",
        views.run_outcomes_chart,
        name="run-outcomes-chart",
    ),

    # --- API (Section 6, owned by Connor) ---
    path("api/datasets/", views.dataset_api, name="dataset-api"),

    # --- A4 Part 3: reports and exports (Hriday) ---
    path("reports/", views.reports_view, name="reports"),
    path(
        "reports/export/validation-runs.csv",
        views.export_validation_runs_csv,
        name="export-validation-runs-csv",
    ),
    path(
        "reports/export/validation-runs.json",
        views.export_validation_runs_json,
        name="export-validation-runs-json",
    ),
]
