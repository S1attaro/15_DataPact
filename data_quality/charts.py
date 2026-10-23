"""
Server-side chart rendering for DataPact - A3 Section 4, Tejas Jaggi.

The aggregation and the drawing live here rather than in views.py so that the
numbers behind a chart can be tested without going through HTTP, and so the
view stays a thin wrapper around "get the data, draw it, return the bytes".

Matplotlib is pinned to the Agg backend, which draws into memory with no
window system - what a web server needs, and what stops an import from failing
on a machine with no display.

Drawing goes through Figure/FigureCanvasAgg rather than pyplot. pyplot keeps a
single process-wide registry of every figure it creates, and Django serves
requests on threads (runserver does by default, and so does any real WSGI
server), so two people loading the chart at the same time would be mutating
that shared registry from two threads at once. A Figure built directly owns no
global state: it is an ordinary object that is garbage-collected when the
request ends, so there is nothing to leak and nothing to race on.
"""

from io import BytesIO

import matplotlib

matplotlib.use("Agg")

from django.db.models import Count, Sum  # noqa: E402  (after matplotlib.use)
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

from .models import ValidationRun  # noqa: E402

# The same three colours the status badges use elsewhere in the site
# (--pass-ink / --fail-ink / --warn-ink in base.html), so a run that reads as
# "failed" in a table reads as the same colour in the chart.
RUN_STATUS_COLORS = {
    ValidationRun.Status.PASSED: "#1d6b36",
    ValidationRun.Status.FAILED: "#a12a2a",
    ValidationRun.Status.ERROR: "#855c11",
}

FIGURE_SIZE = (7.2, 4.0)
FIGURE_DPI = 110

# The chart's own title (A3 Section 4 asks for a title, labels and a
# legend on the image). The Quality History panel around it is headed
# "As a chart", so the page does not say the same words twice.
RUN_OUTCOMES_TITLE = "Validation run outcomes"

# Text and line colours from datapact.css (UX Stage 6): --ink, --ink-soft
# and --line-strong. The notes used to be #8b959f, 2.9:1 on white.
INK = "#16202c"
INK_SOFT = "#5a6672"
LINE_STRONG = "#7d8792"
GRID = "#e3e7ec"


def run_outcome_counts():
    """
    How many validation runs ended in each outcome.

    Returns a list of ``(status value, human label, count)`` in the order the
    statuses are declared on the model, e.g.::

        [("PASSED", "Passed", 4), ("FAILED", "Failed", 7), ("ERROR", "Error", 1)]

    The grain is one ValidationRun: one file checked against one contract
    version. Runs against retired contract versions are included, because the
    outcome of a check that already happened does not stop being history when
    the contract it used is superseded.

    A status with no runs is reported as 0 rather than dropped, so the chart
    keeps a fixed set of bars, and the ordering comes from the model rather
    than from whatever order the database returns rows in.
    """
    totals = {
        row["status"]: row["total"]
        for row in ValidationRun.objects.values("status").annotate(total=Count("id"))
    }
    return [
        (value, label, totals.get(value, 0))
        for value, label in ValidationRun.Status.choices
    ]


def run_outcome_rows():
    """
    Chart-ready rows for the outcome bar chart (A4 Part 1).

    Same aggregation as run_outcome_counts(), reshaped into the flat
    ``[{"outcome": ..., "runs": ...}]`` form Vega-Lite reads directly. Statuses
    with no runs are kept at zero so the chart has a stable set of bars.
    """
    return [
        {"outcome": label, "runs": total}
        for _, label, total in run_outcome_counts()
    ]


def run_volume_points():
    """
    Chart-ready rows for the rows-checked vs rows-failed scatter (A4 Part 1).

    One point per ValidationRun: the grain is one file checked against one
    contract version. ``rows_failed`` sums the failed_row_count of that run's
    violations, and a run with no violations is 0 rather than null, so a clean
    run still plots on the floor of the chart instead of disappearing.
    """
    runs = (
        ValidationRun.objects
        .select_related("contract__dataset")
        .annotate(failed=Sum("violations__failed_row_count"))
        .order_by("started_at")
    )
    labels = dict(ValidationRun.Status.choices)
    return [
        {
            "file_name": run.file_name,
            "dataset": run.contract.dataset.name,
            "rows_checked": run.row_count,
            "rows_failed": run.failed or 0,
            "outcome": labels[run.status],
            "started_at": run.started_at.date().isoformat(),
        }
        for run in runs
    ]


def build_run_outcomes_figure():
    """
    Draw the run-outcome chart as a Figure (the PNG endpoint saves it).

    Separate from the rendering so tests can read the title, labels, legend
    and colours off the figure instead of guessing at pixels.

    Text sizes (UX Stage 6): nothing is under 11pt. The 792px image is
    shown about 310px wide on a 390px phone, where the old 9-10pt notes and
    labels came out near 5 CSS px; at 11-12pt they are about 6.5-7px. It is
    still a small picture there, which is why the text table under it gives
    the same numbers as page text.
    """
    outcomes = run_outcome_counts()
    labels = [label for _, label, _ in outcomes]
    counts = [count for _, _, count in outcomes]
    colors = [RUN_STATUS_COLORS[value] for value, _, _ in outcomes]
    total = sum(counts)

    fig = Figure(figsize=FIGURE_SIZE, dpi=FIGURE_DPI)
    FigureCanvasAgg(fig)
    ax = fig.subplots()

    bars = ax.bar(labels, counts, color=colors, width=0.55, zorder=2)

    ax.set_title(RUN_OUTCOMES_TITLE, fontsize=15, fontweight="bold", pad=16, color=INK)
    ax.set_xlabel("Outcome", fontsize=12, labelpad=10, color=INK)
    ax.set_ylabel("Validation runs", fontsize=12, labelpad=10, color=INK)

    # Whole runs only - "2.5 runs" is not a thing.
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    # Headroom so the value printed above the tallest bar is not clipped.
    ax.set_ylim(0, max(max(counts) * 1.22, 1))

    ax.bar_label(bars, padding=4, fontsize=12, fontweight="bold", color=INK)
    # loc="best" rather than a fixed corner: which bar is tallest depends on
    # the data, and a pinned legend would eventually sit on top of one.
    legend = ax.legend(bars, labels, title="Outcome", frameon=False, fontsize=11,
                       title_fontsize=11, loc="best", labelcolor=INK)
    legend.get_title().set_color(INK)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    # The baseline the bars stand on: --line-strong, 3.65:1 (it was the
    # grid's own #e3e7ec, 1.25:1, and all but vanished).
    ax.spines["bottom"].set_color(LINE_STRONG)
    ax.tick_params(axis="both", length=0, labelsize=12, colors=INK_SOFT)

    if total:
        fig.text(
            0.5, 0.015,
            f"{total} validation run{'' if total == 1 else 's'} recorded",
            ha="center", fontsize=11, color=INK_SOFT,
        )
    else:
        # Say so on the image itself: an all-zero chart with no explanation
        # looks like something failed to load.
        ax.text(
            0.5, 0.5, "No validation runs recorded yet",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=13, color=INK_SOFT,
        )

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def render_run_outcomes_png():
    """Draw the run-outcome chart and return it as PNG bytes."""
    fig = build_run_outcomes_figure()
    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()
