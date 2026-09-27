from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views import View
from django.views.generic import DetailView, ListView

from .models import Contract, Dataset, Violation


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
# Section 2: ORM queries, search (GET + POST), aggregations
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class ContractSearchView(View):
    """GET searches Contract, POST looks up Violation (kept off GET since
    sample_values can hold raw values from the source file)."""

    template_name = "data_quality/contract_search.html"

    def _status_breakdown(self):
        return (
            Contract.objects.values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )

    def get(self, request):
        contracts = Contract.objects.select_related("dataset")

        query = request.GET.get("q", "").strip()
        status = request.GET.get("status", "").strip()

        filtered_contracts = contracts
        if query:
            filtered_contracts = filtered_contracts.filter(
                dataset__name__icontains=query
            )
        if status:
            filtered_contracts = filtered_contracts.filter(status__exact=status)

        context = {
            "total_contracts": contracts.count(),
            "status_breakdown": self._status_breakdown(),
            "filtered_contracts": filtered_contracts,
            "query": query,
            "status": status,
            "status_choices": Contract.Status.choices,
            "resolution_choices": Violation.Resolution.choices,
            "violation_query": "",
            "violation_resolution": "",
            "violation_results": None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        violation_query = request.POST.get("dataset", "").strip()
        violation_resolution = request.POST.get("resolution", "").strip()

        violation_results = Violation.objects.select_related(
            "rule", "rule__contract", "rule__contract__dataset"
        )
        if violation_query:
            violation_results = violation_results.filter(
                rule__contract__dataset__name__icontains=violation_query
            )
        if violation_resolution:
            violation_results = violation_results.filter(
                resolution__exact=violation_resolution
            )

        contracts = Contract.objects.select_related("dataset")
        context = {
            "total_contracts": contracts.count(),
            "status_breakdown": self._status_breakdown(),
            "filtered_contracts": contracts,
            "query": "",
            "status": "",
            "status_choices": Contract.Status.choices,
            "resolution_choices": Violation.Resolution.choices,
            "violation_query": violation_query,
            "violation_resolution": violation_resolution,
            "violation_results": violation_results,
        }
        return render(request, self.template_name, context)


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
