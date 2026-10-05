import csv
from io import StringIO
import requests

from django.contrib import messages
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views import View
from django.views.generic import DetailView, ListView

from . import charts
from .forms import DatasetForm
from .models import Contract, Dataset, ValidationRun, Violation


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
# Section 5: forms and user input
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class DatasetManageView(View):
    """GET filters the dataset list by source team, POST registers a new
    one (Post/Redirect/Get on success)."""

    template_name = "data_quality/dataset_manage.html"

    def _datasets(self, team):
        datasets = Dataset.objects.select_related("owner")
        if team:
            datasets = datasets.filter(source_team__icontains=team)
        return datasets

    def get(self, request):
        team = request.GET.get("team", "").strip()
        context = {
            "datasets": self._datasets(team),
            "team": team,
            "form": DatasetForm(),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        team = request.POST.get("team", "").strip()
        form = DatasetForm(request.POST)

        if form.is_valid():
            dataset = form.save()
            messages.success(request, f'Registered dataset "{dataset.name}".')
            return redirect(dataset.get_absolute_url())

        context = {
            "datasets": self._datasets(team),
            "team": team,
            "form": form,
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


# ---------------------------------------------------------------
# API views (Section 6)
# Author: Connor Slattery (cslat)
# ---------------------------------------------------------------

def dataset_api(request):
    """
    JSON API for the dataset registry. Returns JsonResponse
    (application/json), unlike dataset_manual above which returns
    HttpResponse (text/html) for the same data.

    Optional filters via query params:
      ?owner=cslat
      ?source_team=Operations
    """
    datasets = Dataset.objects.select_related("owner")

    owner = request.GET.get("owner")
    if owner:
        datasets = datasets.filter(owner__username=owner)

    source_team = request.GET.get("source_team")
    if source_team:
        datasets = datasets.filter(source_team__iexact=source_team)

    data = [
        {
            "id": dataset.id,
            "name": dataset.name,
            "owner": dataset.owner.username,
            "source_team": dataset.source_team,
            "description": dataset.description,
            "created_at": dataset.created_at.isoformat(),
        }
        for dataset in datasets
    ]

    return JsonResponse({"count": len(data), "datasets": data})


# ---------------------------------------------------------------
# Home page, navigation and quality analytics (A3 Sections 1 and 4)
# Author: Tejas Jaggi (tejasj2)
# ---------------------------------------------------------------


def home(request):
    """
    Landing page at the site root.

    Before this existed, "/" was a 404 and the only way into the site was to
    know a URL by heart. It is deliberately small: three counts that say
    whether there is anything to look at, and a signpost to each real section.
    """
    context = {
        "dataset_count": Dataset.objects.count(),
        "run_count": ValidationRun.objects.count(),
        "open_violation_count": Violation.objects.filter(
            resolution=Violation.Resolution.OPEN
        ).count(),
    }
    return render(request, "data_quality/home.html", context)


def quality_history(request):
    """
    Quality History: how validation runs have been turning out.

    The page shows the chart image and the same numbers in a table, so the
    figures are available to a screen reader and to anyone who cannot see the
    image, not only to someone looking at the picture.
    """
    outcomes = charts.run_outcome_counts()
    context = {
        "outcomes": outcomes,
        "run_total": sum(total for _, _, total in outcomes),
    }
    return render(request, "data_quality/quality_history.html", context)


def run_outcomes_chart(request):
    """
    The Quality History chart as a PNG, served straight from memory.

    Matplotlib writes into a BytesIO buffer rather than a file on disk: the
    image is derived from the database and changes whenever a run is recorded,
    so writing it out would mean owning a cache and its invalidation for a
    picture that takes milliseconds to draw.
    """
    return HttpResponse(charts.render_run_outcomes_png(), content_type="image/png")


# ---------------------------------------------------------------
# A4 Part 3: reports, grouped summaries, CSV/JSON export
# Author: Hriday Agarwal
# ---------------------------------------------------------------

def _validation_runs_queryset():
    return ValidationRun.objects.select_related(
        "contract", "contract__dataset", "submitted_by"
    ).order_by("-started_at")


def reports_view(request):
    """
    Reports page: two grouped summaries over ValidationRun (by outcome, and
    by dataset) plus a totals line, with links to export the same data.

    The outcome breakdown reuses charts.run_outcome_counts() rather than
    recomputing it, so this page and the Quality History chart can never
    disagree about how many runs passed, failed, or errored.
    """
    runs = _validation_runs_queryset()

    dataset_breakdown = (
        runs.values("contract__dataset__name")
        .annotate(total=Count("id"))
        .order_by("contract__dataset__name")
    )

    context = {
        "status_breakdown": charts.run_outcome_counts(),
        "dataset_breakdown": dataset_breakdown,
        "dataset_total": Dataset.objects.count(),
        "run_total": runs.count(),
        "failed_total": runs.filter(status=ValidationRun.Status.FAILED).count(),
    }
    return render(request, "data_quality/reports.html", context)


def export_validation_runs_csv(request):
    """CSV export of every ValidationRun, newest first."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id", "file_name", "dataset", "contract_version", "status",
        "submitted_by", "row_count", "started_at", "finished_at",
    ])
    for run in _validation_runs_queryset():
        writer.writerow([
            run.id,
            run.file_name,
            run.contract.dataset.name,
            run.contract.version_number,
            run.status,
            run.submitted_by.username if run.submitted_by else "",
            run.row_count,
            run.started_at.isoformat(),
            run.finished_at.isoformat() if run.finished_at else "",
        ])

    filename = f"validation_runs_{timezone.now():%Y-%m-%d_%H-%M}.csv"
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_validation_runs_json(request):
    """JSON export of every ValidationRun, with generated_at/record_count metadata."""
    runs = _validation_runs_queryset()
    data = {
        "generated_at": timezone.now().isoformat(),
        "record_count": runs.count(),
        "validation_runs": [
            {
                "id": run.id,
                "file_name": run.file_name,
                "dataset": run.contract.dataset.name,
                "contract_version": run.contract.version_number,
                "status": run.status,
                "submitted_by": run.submitted_by.username if run.submitted_by else None,
                "row_count": run.row_count,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            }
            for run in runs
        ],
    }
    filename = f"validation_runs_{timezone.now():%Y-%m-%d_%H-%M}.json"
    response = JsonResponse(data, json_dumps_params={"indent": 2})
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


# ---------------------------------------------------------------
# A4 Part 2: external API integration
# Author: Connor Slattery (cslat)
# ---------------------------------------------------------------

def dataset_lookup_api(request):
    """
    Combines our internal Dataset registry with Open Library's public
    search API (https://openlibrary.org/search.json), keyed off the same
    query term. Nothing from Open Library is stored; the external response
    is processed in memory and returned alongside our own data.

    Usage: /api/lookup/?q=<term>
    Matches internal datasets whose name, description, or source_team
    contains the term, and external book results whose title contains it.
    """
    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse(
            {"error": "Query parameter 'q' is required, e.g. ?q=enrollment"},
            status=400,
        )

    internal_matches = Dataset.objects.select_related("owner").filter(
        name__icontains=query
    ) | Dataset.objects.select_related("owner").filter(
        description__icontains=query
    ) | Dataset.objects.select_related("owner").filter(
        source_team__icontains=query
    )
    internal_matches = internal_matches.distinct()

    internal_data = [
        {
            "id": dataset.id,
            "name": dataset.name,
            "source_team": dataset.source_team,
            "description": dataset.description,
        }
        for dataset in internal_matches
    ]

    try:
        response = requests.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5},
            timeout=5,
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return JsonResponse(
            {"error": "The external API timed out. Try again."},
            status=504,
        )
    except requests.exceptions.RequestException as exc:
        return JsonResponse(
            {"error": f"The external API request failed: {exc}"},
            status=502,
        )

    external_raw = response.json().get("docs", [])
    external_data = [
        {
            "title": doc.get("title"),
            "author": (doc.get("author_name") or [None])[0],
            "first_publish_year": doc.get("first_publish_year"),
        }
        for doc in external_raw[:5]
    ]

    return JsonResponse(
        {
            "query": query,
            "internal_match_count": len(internal_data),
            "internal_matches": internal_data,
            "external_match_count": len(external_data),
            "external_matches": external_data,
        }
    )