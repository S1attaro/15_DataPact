from django.urls import path

from . import views

app_name = "data_quality"

urlpatterns = [
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
]
