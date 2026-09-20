from django.urls import path

from . import views

app_name = "data_quality"

urlpatterns = [
    # --- CBVs (this section owned by Hriday) ---
    path("datasets/overview/", views.DatasetOverviewView.as_view(), name="dataset-cbv-base"),
    path("datasets/", views.DatasetListView.as_view(), name="dataset-list"),
    path("datasets/<int:pk>/", views.DatasetDetailView.as_view(), name="dataset-detail"),

    # --- FBVs (teammate section - add here once written) ---
    # path("datasets/manual/", views.dataset_manual, name="dataset-manual"),
    # path("datasets/render/", views.dataset_render, name="dataset-render"),
]
