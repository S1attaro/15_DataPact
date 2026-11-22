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

# The three colours the status badges use (--pass-ink / --fail-ink /
# --warn-ink in datapact.css, the Pass / Fail / Warn inks of DESIGN.md), so a
# run that reads as "failed" in a table reads as the same colour in the chart.
# Stage 3E: these were the pre-redesign values (#1d6b36, #a12a2a, #855c11).
RUN_STATUS_COLORS = {
    ValidationRun.Status.PASSED: "#1a5f32",
    ValidationRun.Status.FAILED: "#9f2718",
    ValidationRun.Status.ERROR: "#7a5207",
}

FIGURE_SIZE = (7.2, 4.0)
FIGURE_DPI = 110

# Stage 3E: two drawings of the same chart. "wide" is the desktop image
# (792 x 440 px, shown at its own size). "narrow" is drawn for a phone rather
# than scaled down from the wide one: 640 x 680 px at 200 dpi, served as a 2x
# image, so it is shown 320 x 340 CSS px and one point of type is
# 200 / 72 / 2 = 1.39 CSS px. Its smallest text (9.5pt) is about 13 CSS px.
# The wide image's 11pt text was about 6.5 CSS px on a 390px phone.
LAYOUTS = {
    "wide": {
        "figsize": FIGURE_SIZE, "dpi": FIGURE_DPI,
        "title": 15, "axis": 12, "ticks": 12, "values": 12, "legend": 11, "note": 11, "empty": 13,
    },
    "narrow": {
        "figsize": (3.2, 3.4), "dpi": 200,
        "title": 12, "axis": 10, "ticks": 10, "values": 10, "legend": 9.5, "note": 9.5, "empty": 10,
    },
}
NARROW_DENSITY = 2  # the narrow image is served at 2x: CSS size = pixel size / 2

# The chart's own title (A3 Section 4 asks for a title, labels and a
# legend on the image). The Quality History panel around it is headed
# "As a chart", so the page does not say the same words twice.
RUN_OUTCOMES_TITLE = "Validation run outcomes"

# Text and line colours from datapact.css: --ink (Graphite), --ink-soft
# (Soft Graphite), --line-strong (Field Edge) and --line (Rule Line). Stage 3E
# moved them to the design system's values (they were #16202c, #5a6672,
# #7d8792 and #e3e7ec). The font is matplotlib's bundled DejaVu Sans: Archivo
# ships only as a web font (woff2), which matplotlib cannot read.
INK = "#121b20"
INK_SOFT = "#46545b"
LINE_STRONG = "#77878d"
GRID = "#dde3e3"


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


def build_run_outcomes_figure(layout="wide"):
    """
    Draw the run-outcome chart as a Figure (the PNG endpoint saves it).

    ``layout`` is "wide" (the desktop image, the default) or "narrow" (the
    phone image, Stage 3E); anything else raises KeyError. Same data, title,
    axis labels, legend and colours in both; only size, type and the legend's
    place change. On the narrow image the legend sits above the plot in one
    row, so it can never cover a bar in a plot that narrow.

    Separate from the rendering so tests can read the title, labels, legend
    and colours off the figure instead of guessing at pixels.

    Text sizes: nothing on the wide image is under 11pt (UX Stage 6). Since
    Stage 3E a phone no longer gets the wide image scaled down (it was shown
    about 310px wide on a 390px phone, where 11-12pt came out near 6.5-7 CSS
    px): Quality History serves it the "narrow" drawing instead, whose
    smallest text is about 13 CSS px (see LAYOUTS). The text table under the
    chart still gives the same numbers as page text.
    """
    size = LAYOUTS[layout]
    outcomes = run_outcome_counts()
    labels = [label for _, label, _ in outcomes]
    counts = [count for _, _, count in outcomes]
    colors = [RUN_STATUS_COLORS[value] for value, _, _ in outcomes]
    total = sum(counts)

    fig = Figure(figsize=size["figsize"], dpi=size["dpi"])
    FigureCanvasAgg(fig)
    ax = fig.subplots()

    bars = ax.bar(labels, counts, color=colors, width=0.55, zorder=2)

    ax.set_title(RUN_OUTCOMES_TITLE, fontsize=size["title"], fontweight="bold",
                 pad=48 if layout == "narrow" else 16, color=INK)
    ax.set_xlabel("Outcome", fontsize=size["axis"], labelpad=10, color=INK)
    ax.set_ylabel("Validation runs", fontsize=size["axis"], labelpad=10, color=INK)

    # Whole runs only - "2.5 runs" is not a thing.
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    # Headroom so the value printed above the tallest bar is not clipped.
    ax.set_ylim(0, max(max(counts) * 1.22, 1))

    ax.bar_label(bars, padding=4, fontsize=size["values"], fontweight="bold", color=INK)
    if layout == "narrow":
        # One row above the plot: a 320px-wide plot has no free corner.
        legend = ax.legend(bars, labels, title="Outcome", frameon=False, fontsize=size["legend"],
                           title_fontsize=size["legend"], loc="lower center", bbox_to_anchor=(0.5, 1.0),
                           ncol=3, labelcolor=INK, handlelength=1.0, columnspacing=1.0,
                           alignment="center")
    else:
        # loc="best" rather than a fixed corner: which bar is tallest depends on
        # the data, and a pinned legend would eventually sit on top of one.
        legend = ax.legend(bars, labels, title="Outcome", frameon=False, fontsize=size["legend"],
                           title_fontsize=size["legend"], loc="best", labelcolor=INK)
    legend.get_title().set_color(INK)

    ax.grid(axis="y", color=GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    # The baseline the bars stand on: --line-strong, 3.65:1 (it was the
    # grid's own #e3e7ec, 1.25:1, and all but vanished).
    ax.spines["bottom"].set_color(LINE_STRONG)
    ax.tick_params(axis="both", length=0, labelsize=size["ticks"], colors=INK_SOFT)

    if total:
        fig.text(
            0.5, 0.015,
            f"{total} validation run{'' if total == 1 else 's'} recorded",
            ha="center", fontsize=size["note"], color=INK_SOFT,
        )
    else:
        # Say so on the image itself: an all-zero chart with no explanation
        # looks like something failed to load.
        ax.text(
            0.5, 0.5, "No validation runs recorded yet",
            transform=ax.transAxes, ha="center", va="center",
            fontsize=size["empty"], color=INK_SOFT,
        )

    fig.tight_layout(rect=(0, 0.05, 1, 1))
    return fig


def render_run_outcomes_png(layout="wide"):
    """Draw the run-outcome chart (wide or narrow) and return it as PNG bytes."""
    fig = build_run_outcomes_figure(layout)
    buffer = BytesIO()
    fig.savefig(buffer, format="png")
    return buffer.getvalue()
