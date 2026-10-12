from django.urls import path

from . import auth_views, views

app_name = "data_quality"

urlpatterns = [
    # --- A5.1 Part 1: authentication (Tejas) ---
    #
    # Mounted under accounts/ because that is where Django and allauth both
    # expect auth URLs to live. HRIDAY: allauth also claims accounts/login/,
    # accounts/signup/ and accounts/logout/. Mount it so it does not shadow
    # these three (its social URLs are the part Part 2 needs), or tell me and
    # I will switch these over to allauth's views instead - either works, but
    # we have to pick one rather than both defining the same path.
    path("accounts/login/", auth_views.DataPactLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.DataPactLogoutView.as_view(), name="logout"),
    path("accounts/signup/", auth_views.signup, name="signup"),

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

    # --- A4 Part 1: chart APIs and Vega-Lite charts (Tejas) ---
    path("charts/", views.charts_page, name="charts"),
    path("api/run-outcomes/", views.api_run_outcomes, name="api-run-outcomes"),
    path("api/run-volume/", views.api_run_volume, name="api-run-volume"),
    path(
        "vega-lite/chart<int:number>.json",
        views.vega_chart_spec,
        name="vega-chart-spec",
    ),

    # --- A4 Part 2: external API (Connor) ---
    path("api/lookup/", views.dataset_lookup_api, name="dataset-lookup"),

    # --- A5: alternative API-use demos (Connor) ---
    path("demos/fetch/", views.demo4_fetch_page, name="demo4-fetch-page"),

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
