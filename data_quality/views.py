from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views import View
from django.views.generic import DetailView, ListView

from .models import Contract, Dataset


class DatasetOverviewView(View):
    """
    Base CBV (inherits django.views.View).

    Manually queries Dataset the same way a ListView would, but also
    hand-computes a per-dataset contract count and the dataset's current
    active contract. A generic ListView's context only ever holds what
    Dataset itself stores, so anything that has to be derived by walking a
    relation (active contract, counts) needs a view that builds its own
    context by hand - this is exactly that case.
    """

    template_name = "data_quality/dataset_overview.html"

    def get(self, request):
        datasets = Dataset.objects.select_related("owner").prefetch_related("contracts")

        rows = []
        for dataset in datasets:
            active_contract = next(
                (c for c in dataset.contracts.all() if c.status == Contract.Status.ACTIVE),
                None,
            )
            rows.append(
                {
                    "dataset": dataset,
                    "contract_count": len(dataset.contracts.all()),
                    "active_contract": active_contract,
                }
            )

        context = {"rows": rows}
        return render(request, self.template_name, context)


class DatasetListView(ListView):
    """
    Generic CBV: plain registry list of every Dataset, newest-name-first
    (Dataset.Meta.ordering). Mirrors wireframe screen 1 (Dashboard / Dataset
    Registry).
    """

    model = Dataset
    template_name = "data_quality/dataset_list.html"
    context_object_name = "datasets"

    def get_queryset(self):
        return Dataset.objects.select_related("owner")


class DatasetDetailView(DetailView):
    """
    Generic CBV: one dataset with its contract version history. Mirrors
    wireframe screen 2 (Dataset Detail).
    """

    model = Dataset
    template_name = "data_quality/dataset_detail.html"
    context_object_name = "dataset"

    def get_queryset(self):
        return Dataset.objects.select_related("owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["contracts"] = self.object.contracts.all()
        return context

# ---------------------------------------------------------------
# Function-based views
# Author: Connor Slattery (cslat)
# ---------------------------------------------------------------

# View 1: HttpResponse (manual)
def dataset_manual(request):
    datasets = Dataset.objects.all()

    html = "<h1>DataPact: Datasets (manual HttpResponse)</h1>"
    html += "<p>{} datasets registered.</p>".format(datasets.count())
    html += "<ul>"
    for dataset in datasets:
        html += "<li>{}</li>".format(escape(dataset.name))
    html += "</ul>"

    return HttpResponse(html)


# View 2: render() (shortcut)
def dataset_render(request):
    """
    Same dataset registry as DatasetListView, but built by a plain function:
    query the model, put the queryset in a context dict, hand both to
    render(). It reuses dataset_list.html on purpose - the template does not
    care whether a generic CBV or a function supplied the "datasets" key.
    """
    datasets = Dataset.objects.select_related("owner")
    context = {
        "datasets": datasets,
        # Optional caption dataset_list.html shows under the title; without it
        # the template names the ListView, which would be wrong here.
        "view_label": "Function-based view - render()",
    }
    return render(request, "data_quality/dataset_list.html", context)
