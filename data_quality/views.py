import csv
import os
from io import StringIO
import requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Case, CharField, Count, OuterRef, Q, Subquery, Value, When
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.html import escape
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import DetailView, ListView

from . import charts, vega
from .access import api_login_required, public_api
from .forms import DatasetForm
from .models import Contract, Dataset, ValidationRun, Violation


class DatasetOverviewView(LoginRequiredMixin, View):
    """
    Base CBV (inherits django.views.View).

    Manually queries Dataset the same way a ListView would, but also
    hand-computes a per-dataset contract count and the dataset's current
    active contract. A generic ListView's context only ever holds what
    Dataset itself stores, so anything that has to be derived by walking a
    relation (active contract, counts) needs a view that builds its own
    context by hand - this is exactly that case.

    Product redesign, Stage 3C: the page became the workspace overview. The
    context the A2 table needs is unchanged ("rows", each with "dataset",
    "contract_count" and "active_contract"); around it the view now builds,
    by hand as before:

      open_violations / open_violation_count  the five most recent open
                       violations (newest run first) and the total
      recent_runs / run_count  the five most recently recorded runs with
                       their violation and open-violation counts, and the total
      gaps             datasets with no active contract, with no recorded run,
                       or whose latest run ended in an error

    Five queries in all, however many rows there are: the datasets (with the
    registry's run and violation annotations), their contracts (prefetched),
    the open violations, their count, and the recent runs. The gaps and the
    run total are read from the dataset rows already fetched.
    """

    template_name = "data_quality/dataset_overview.html"
    LIST_SIZE = 5

    def get(self, request):
        datasets = registry_queryset().prefetch_related("contracts")

        rows = []
        gaps = {"no_active_contract": [], "no_runs": [], "latest_run_error": []}
        run_count = 0
        for dataset in datasets:
            contracts = dataset.contracts.all()
            active_contract = next(
                (c for c in contracts if c.status == Contract.Status.ACTIVE),
                None,
            )
            rows.append(
                {
                    "dataset": dataset,
                    "contract_count": len(contracts),
                    "active_contract": active_contract,
                }
            )
            run_count += dataset.run_count
            if active_contract is None:
                gaps["no_active_contract"].append(dataset)
            if not dataset.run_count:
                gaps["no_runs"].append(dataset)
            elif dataset.latest_run_status == ValidationRun.Status.ERROR:
                gaps["latest_run_error"].append(dataset)

        open_violations = Violation.objects.filter(resolution=Violation.Resolution.OPEN)
        recent_runs = (
            ValidationRun.objects.select_related("contract", "contract__dataset")
            .annotate(
                violation_count=Count("violations", distinct=True),
                open_count=Count(
                    "violations",
                    filter=Q(violations__resolution=Violation.Resolution.OPEN),
                    distinct=True,
                ),
            )
            .order_by("-started_at", "-pk")[: self.LIST_SIZE]
        )

        context = {
            "rows": rows,
            "open_violations": list(
                open_violations.select_related(
                    "run", "rule", "rule__contract", "rule__contract__dataset"
                ).order_by("-run__started_at", "-run_id", "-failed_row_count", "pk")[: self.LIST_SIZE]
            ),
            "open_violation_count": open_violations.count(),
            "recent_runs": list(recent_runs),
            "run_count": run_count,
            "gaps": gaps,
            "has_gaps": any(gaps.values()),
        }
        return render(request, self.template_name, context)


def registry_queryset():
    """
    Every dataset with the facts the registry shows beside it, in ONE query
    (product redesign, Stage 3A). Read-only annotations over existing
    relations; nothing here changes what a dataset, run or violation means.

      active_version        version_number of the ACTIVE contract, or None
      run_count             validation runs recorded against any version
      latest_run_at/status  the most recent run (started_at, then pk)
      latest_run_label      that status's display name ("Failed")
      open_violation_count  violations still OPEN, the same definition the
                            dataset page and the home page use

    Ordered by name, as Dataset.Meta.ordering is, written out so the
    aggregation cannot drop it.
    """
    runs = ValidationRun.objects.filter(contract__dataset=OuterRef("pk")).order_by("-started_at", "-pk")
    active = Contract.objects.filter(
        dataset=OuterRef("pk"), status=Contract.Status.ACTIVE
    ).order_by("-version_number")
    return (
        Dataset.objects.select_related("owner")
        .annotate(
            active_version=Subquery(active.values("version_number")[:1]),
            run_count=Count("contracts__runs", distinct=True),
            latest_run_at=Subquery(runs.values("started_at")[:1]),
            latest_run_status=Subquery(runs.values("status")[:1]),
            open_violation_count=Count(
                "contracts__rules__violations",
                filter=Q(contracts__rules__violations__resolution=Violation.Resolution.OPEN),
                distinct=True,
            ),
        )
        .annotate(
            latest_run_label=Case(
                *(When(latest_run_status=value, then=Value(label)) for value, label in ValidationRun.Status.choices),
                default=Value(""),
                output_field=CharField(),
            )
        )
        .order_by(*Dataset._meta.ordering)
    )


class DatasetListView(LoginRequiredMixin, ListView):
    """
    Generic CBV: the dataset registry, ordered by name (Dataset.Meta.ordering).
    Mirrors wireframe screen 1 (Dashboard / Dataset Registry).

    Product redesign, Stage 3A: each row also carries its active contract
    version, latest run and open violations (registry_queryset()), and the
    page can be narrowed with two GET parameters:

      q     text found in the dataset's name, source team or owner's username
      show  "open" keeps only datasets with at least one open violation

    Both are plain GET, so a filtered view is a link that can be shared, and
    the form works without JavaScript.
    """

    model = Dataset
    template_name = "data_quality/dataset_list.html"
    context_object_name = "datasets"

    SHOW_OPEN = "open"
    MAX_QUERY = 100

    def filters(self):
        query = self.request.GET.get("q", "").strip()[: self.MAX_QUERY]
        show = self.request.GET.get("show", "")
        return query, (show if show == self.SHOW_OPEN else "")

    def get_queryset(self):
        query, show = self.filters()
        datasets = registry_queryset()
        if query:
            datasets = datasets.filter(
                Q(name__icontains=query)
                | Q(source_team__icontains=query)
                | Q(owner__username__icontains=query)
            )
        if show == self.SHOW_OPEN:
            datasets = datasets.filter(open_violation_count__gt=0)
        return datasets

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query, show = self.filters()
        # The summary describes the whole registry, never just the filtered
        # rows, so it reads the same whatever the search box holds.
        everything = list(registry_queryset())
        context["registry_columns"] = True
        context["registry"] = {
            "query": query,
            "show": show,
            "filtered": bool(query or show),
            "total": len(everything),
            "with_active_contract": sum(1 for d in everything if d.active_version is not None),
            "with_runs": sum(1 for d in everything if d.run_count),
            "needing_decision": sum(1 for d in everything if d.open_violation_count),
        }
        return context


class DatasetDetailView(LoginRequiredMixin, DetailView):
    """
    Generic CBV: one dataset with its contract version history. Mirrors
    wireframe screen 2 (Dataset Detail). UX Stage 4 adds its recorded
    violations, so a dataset's failures can be found from its own page.
    """

    model = Dataset
    template_name = "data_quality/dataset_detail.html"
    context_object_name = "dataset"

    def get_queryset(self):
        return Dataset.objects.select_related("owner")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Stage 3G: the rule count is annotated in the same query (it was one
        # COUNT per version from the template), and the list is evaluated once
        # so the table, the summary and the empty states read the same rows.
        contracts = list(
            self.object.contracts.annotate(rule_count=Count("rules")).order_by("-version_number")
        )
        context["contracts"] = contracts

        # Stage 3G: every recorded run, newest first, in one query. Nothing is
        # cut off: the page says how many there are and lists them all.
        runs = list(
            ValidationRun.objects.filter(contract__dataset=self.object)
            .select_related("contract")
            .order_by("-started_at", "-pk")
        )
        context["runs"] = runs

        # UX Stage 4: every violation recorded against any of this dataset's
        # contract versions, newest run first (a run's rows kept together,
        # the most failed rows first within it), in one query. Evaluated
        # here so the template's count, rows and open count all read the
        # same list.
        violations = list(
            Violation.objects.filter(rule__contract__dataset=self.object)
            .select_related("rule", "rule__contract", "run")
            .order_by("-run__started_at", "-run_id", "-failed_row_count", "pk")
        )
        context["violations"] = violations
        context["open_violation_count"] = sum(
            1 for v in violations if v.resolution == Violation.Resolution.OPEN
        )
        context["standing"] = self._standing(contracts, runs, violations)
        if not violations:
            # Only an empty list needs to know whether any run happened, and
            # whether one ended in an error (so that is not read as a pass).
            # Stage 3G: read from the runs already fetched, not a second query.
            run_count = len(runs)
            error_count = sum(1 for run in runs if run.status == ValidationRun.Status.ERROR)
            if run_count:
                message = f"{run_count} validation run{'s' if run_count != 1 else ''} recorded, none with a violation."
                if error_count:
                    message += f" {error_count} ended in an error and may not have been fully checked."
                context["violations_empty"] = ("No violations recorded for this dataset.", message)
            else:
                context["violations_empty"] = (
                    "No validation runs have been recorded for this dataset yet.",
                    "Violations appear here when a run finds a file that breaks one of its contract rules.",
                )
        return context

    @staticmethod
    def _standing(contracts, runs, violations):
        """
        Stage 3G: the facts behind "Where it stands", worked out from the
        lists the page already holds (no further queries).

        active          the version in force: the highest-numbered Active one
                        (the same choice the Contracts page makes), or None.
        latest_run      the newest recorded run, or None.
        latest_is_other the latest run was checked against a version that is
                        not the active one.
        active_unrun    no recorded run at all used the active version. Only
                        then may the page say "No run recorded under vN yet";
                        an older run under it rules the sentence out.
        """
        active = next((c for c in contracts if c.status == Contract.Status.ACTIVE), None)
        latest_run = runs[0] if runs else None
        return {
            "active": active,
            "latest_run": latest_run,
            "latest_is_other": bool(active and latest_run and latest_run.contract_id != active.pk),
            "active_unrun": bool(active and not any(run.contract_id == active.pk for run in runs)),
            "latest_run_violations": (
                sum(1 for v in violations if v.run_id == latest_run.pk) if latest_run else 0
            ),
        }

# ---------------------------------------------------------------
# Section 2: ORM queries, search (GET + POST), aggregations
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class ContractSearchView(LoginRequiredMixin, View):
    """GET searches Contract, POST looks up Violation (kept off GET since
    sample_values can hold raw values from the source file)."""

    template_name = "data_quality/contract_search.html"

    def _status_breakdown(self):
        return (
            Contract.objects.values("status")
            .annotate(total=Count("id"))
            .order_by("status")
        )

    @staticmethod
    def _with_active_version(contracts):
        """
        Stage 3F: each version also carries its dataset's ACTIVE version number
        (dataset_active_version, None when the dataset has none), so the grouped
        table can name the version in force even when a status filter leaves it
        out. A correlated subquery: the same single query, not one per dataset.
        """
        active = Contract.objects.filter(
            dataset=OuterRef("dataset"), status=Contract.Status.ACTIVE
        ).order_by("-version_number").values("version_number")[:1]
        return contracts.annotate(dataset_active_version=Subquery(active))

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

        # UX Stage 3: a link (Home's open-violation count) can choose the
        # lookup's resolution in advance. It only pre-selects the form; the
        # lookup itself still runs on POST.
        violation_resolution = request.GET.get("resolution", "").strip()
        if violation_resolution not in Violation.Resolution.values:
            violation_resolution = ""

        context = {
            "total_contracts": contracts.count(),
            "status_breakdown": self._status_breakdown(),
            "filtered_contracts": self._with_active_version(filtered_contracts),
            "query": query,
            "status": status,
            "status_choices": Contract.Status.choices,
            "resolution_choices": Violation.Resolution.choices,
            "violation_query": "",
            "violation_resolution": violation_resolution,
            "violation_resolution_label": dict(Violation.Resolution.choices).get(violation_resolution, ""),
            "violation_results": None,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        violation_query = request.POST.get("dataset", "").strip()
        violation_resolution = request.POST.get("resolution", "").strip()

        violation_results = Violation.objects.select_related(
            "rule", "rule__contract", "rule__contract__dataset", "run"
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
            "filtered_contracts": self._with_active_version(contracts),
            "query": "",
            "status": "",
            "status_choices": Contract.Status.choices,
            "resolution_choices": Violation.Resolution.choices,
            "violation_query": violation_query,
            "violation_resolution": violation_resolution,
            "violation_results": violation_results,
            # UX Stage 3: the results summary repeats the filter by its
            # label, and an empty result says whether anything exists at all.
            "violation_resolution_label": dict(Violation.Resolution.choices).get(violation_resolution, ""),
            "violations_recorded": Violation.objects.exists(),
        }
        return render(request, self.template_name, context)


# ---------------------------------------------------------------
# Section 5: forms and user input
# Author: Hriday Agarwal
# ---------------------------------------------------------------

class DatasetManageView(LoginRequiredMixin, View):
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
@login_required
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
@login_required
def dataset_render(request):
    """
    Same dataset registry as DatasetListView, but built by a plain function:
    query the model, put the queryset in a context dict, hand both to
    render(). It reuses dataset_list.html on purpose - the template does not
    care whether a generic CBV or a function supplied the "datasets" key.
    """
    datasets = registry_queryset()
    context = {
        "datasets": datasets,
        # The registry's quality columns (Stage 3A); the search form stays on
        # the ListView, which is the view that reads its parameters.
        "registry_columns": True,
        # Names this view in its own context (the A2 record of which view
        # rendered the page). The page no longer prints it (Stage 3A).
        "view_label": "Function-based view - render()",
    }
    return render(request, "data_quality/dataset_list.html", context)


# ---------------------------------------------------------------
# API views (Section 6)
# Author: Connor Slattery (cslat)
# ---------------------------------------------------------------

@api_login_required
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


@login_required
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


@login_required
def run_outcomes_chart(request):
    """
    The Quality History chart as a PNG, served straight from memory.

    Matplotlib writes into a BytesIO buffer rather than a file on disk: the
    image is derived from the database and changes whenever a run is recorded,
    so writing it out would mean owning a cache and its invalidation for a
    picture that takes milliseconds to draw.

    Stage 3E: ``?layout=narrow`` returns the same chart drawn for a phone
    (Quality History asks for it through <picture> below 40em, so a browser
    fetches one image, never both). Without it, or with any other value, the
    response is the desktop image, as before.
    """
    layout = "narrow" if request.GET.get("layout") == "narrow" else "wide"
    return HttpResponse(charts.render_run_outcomes_png(layout), content_type="image/png")


# ---------------------------------------------------------------
# A4 Part 3: reports, grouped summaries, CSV/JSON export
# Author: Hriday Agarwal
# ---------------------------------------------------------------

def _validation_runs_queryset():
    return ValidationRun.objects.select_related(
        "contract", "contract__dataset", "submitted_by"
    ).order_by("-started_at")


@login_required
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


@login_required
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


@login_required
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
# A4 Part 1: internal chart APIs and Vega-Lite charts
# Author: Tejas Jaggi (tejasj2)
#
# Two GET endpoints returning clean JSON straight from the models, and the
# page that charts them. The APIs are separate from Connor's /api/datasets/:
# that one lists dataset records, while a bar chart needs an aggregate and a
# scatter needs one row per run, so neither chart could read it as-is.
# ---------------------------------------------------------------


@require_GET
@public_api
def api_run_outcomes(request):
    """
    GET /api/run-outcomes/ - validation runs grouped by outcome.

    Chart-ready and nothing else: a flat array of {"outcome", "runs"} with no
    envelope, which is the shape Vega-Lite can point at without a parser.
    """
    return JsonResponse(charts.run_outcome_rows(), safe=False)


@require_GET
@api_login_required
def api_run_volume(request):
    """
    GET /api/run-volume/ - one row per validation run, with the rows checked
    and the rows that failed, for the scatter chart.
    """
    return JsonResponse(charts.run_volume_points(), safe=False)


@require_GET
@api_login_required
def vega_chart_spec(request, number):
    """
    GET /vega-lite/chart<n>.json - the Vega-Lite specification itself.

    Each chart's output is published at its own endpoint, so the spec can be
    opened in the Vega-Lite editor or fetched by anything else, and the page
    below renders from this same URL rather than from a second copy.
    """
    build = vega.CHART_SPECS.get(number)
    if build is None:
        raise Http404(f"No Vega-Lite chart numbered {number}.")
    return JsonResponse(build(), json_dumps_params={"indent": 2})


@login_required
def charts_page(request):
    """The two Vega-Lite charts, embedded on one page."""
    context = {
        "chart_specs": [
            # Stage 3E: each panel is headed by the question its chart
            # answers (the chart carries its own name), and the captions say
            # what to read off it instead of which API it calls.
            {
                "number": 1,
                "title": "How did the checked files turn out?",
                "caption": (
                    "Each bar counts the validation runs that ended in that outcome. "
                    "A run is one file checked against one contract version."
                ),
            },
            {
                "number": 2,
                "title": "Do bigger files fail more often?",
                "caption": (
                    "One point per validation run, placed by its size and by how many "
                    "rows failed. On this data the biggest files are not the ones that break."
                ),
            },
        ],
    }
    return render(request, "data_quality/charts.html", context)


# ---------------------------------------------------------------
# A4 Part 2: external API integration
# Author: Connor Slattery (cslat)
# ---------------------------------------------------------------

@api_login_required
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


def demo4_fetch_page(request):
    """
    Serves the A5 Demo 4 standalone fetch() page from the Django dev
    server itself, so the page and /api/run-outcomes/ share an origin.
    Opening the file directly as file:// triggers the browser's CORS
    block, since Django doesn't send CORS headers.
    """
    demo_path = os.path.join(settings.BASE_DIR, "docs", "demos", "demo4_fetch.html")
    with open(demo_path, "r", encoding="utf-8") as f:
        return HttpResponse(f.read())

