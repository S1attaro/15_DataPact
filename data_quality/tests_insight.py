"""
Product redesign, Stage 3E - the Insight pages: Quality History, Charts, Reports.

What these tests pin (the browser side, rendered sizes and screenshots, is in
docs/redesign/stage_3e/):

* Quality History keeps its A3 chart and its meaning. Below 40em a <picture>
  asks the same route for a drawing made for a phone (?layout=narrow, 2x);
  without the parameter the route serves the desktop image as before.
* Both chart systems use DESIGN.md's tokens: the Pass / Fail / Warn inks for
  outcomes, Graphite and Soft Graphite for text, Rule Line for gridlines.
* The A4 Vega-Lite specs keep their URLs, data URLs, marks and fields, and
  gain one shared config (Archivo, readable sizes, the legend above the plot)
  and a shape per outcome on the scatter.
* Each page says what it is for and points to the other two; no developer
  wording on the Charts page.
* Reports keeps its totals, tables and exports, byte for byte in content.
* No page makes more database queries than before Stage 3E.
"""
import csv
import io
import json
import re
import struct

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality import charts, vega
from data_quality.models import Contract, Dataset, ValidationRun
from data_quality.tests import StylesheetMixin

TOKENS = {"pass": "#1a5f32", "fail": "#9f2718", "warn": "#7a5207", "ink": "#121b20",
          "ink_soft": "#46545b", "line": "#dde3e3", "line_strong": "#77878d"}


def png_size(body):
    assert body[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", body[16:24])


def hex_colour(rgba):
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgba[:3])


class InsightData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("insight_owner", password="pw")
        a = Dataset.objects.create(name="Dataset A", owner=cls.user, source_team="Registrar")
        b = Dataset.objects.create(name="Dataset B", owner=cls.user, source_team="Finance")
        ca = Contract.objects.create(dataset=a, version_number=1, status=Contract.Status.ACTIVE)
        cb = Contract.objects.create(dataset=b, version_number=2, status=Contract.Status.ACTIVE)
        for contract, name, status, rows in ((ca, "a1.csv", "PASSED", 120), (ca, "a2.csv", "FAILED", 13120),
                                             (cb, "b1.csv", "ERROR", 40)):
            ValidationRun.objects.create(contract=contract, file_name=name, row_count=rows, status=status,
                                         submitted_by=cls.user if name == "a1.csv" else None)

    def setUp(self):
        self.client.force_login(self.user)

    def html(self, name):
        return self.client.get(reverse(name)).content.decode()


# --- Quality History: the A3 chart, wide and narrow ------------------------------------------

class QualityChartLayoutTests(InsightData):
    url = "/quality/run-outcomes.png"

    def test_the_route_is_unchanged_and_serves_the_desktop_image_by_default(self):
        self.assertEqual(reverse("data_quality:run-outcomes-chart"), self.url)
        for query in ("", "?layout=wide", "?layout=anything"):
            with self.subTest(query=query):
                response = self.client.get(self.url + query)
                self.assertEqual(response["Content-Type"], "image/png")
                self.assertEqual(png_size(response.content), (792, 440))

    def test_the_narrow_layout_is_drawn_for_a_phone_not_scaled_down(self):
        response = self.client.get(self.url + "?layout=narrow")
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(png_size(response.content), (640, 680))  # shown at 320 x 340 CSS px (2x)
        self.assertEqual(charts.NARROW_DENSITY, 2)

    def test_every_word_on_the_phone_drawing_is_at_least_12_css_px(self):
        layout = charts.LAYOUTS["narrow"]
        fig = charts.build_run_outcomes_figure("narrow")
        ax = fig.axes[0]
        texts = [ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels(),
                 *ax.get_legend().get_texts(), ax.get_legend().get_title(), *fig.texts, *ax.texts]
        for text in texts:
            if text.get_text():
                with self.subTest(text=text.get_text()):
                    css_px = text.get_fontsize() * layout["dpi"] / 72 / charts.NARROW_DENSITY
                    self.assertGreaterEqual(css_px, 12)

    def test_both_drawings_show_the_same_data_title_labels_and_legend(self):
        wide, narrow = (charts.build_run_outcomes_figure(layout).axes[0] for layout in ("wide", "narrow"))
        for ax in (wide, narrow):
            self.assertEqual(ax.get_title(), charts.RUN_OUTCOMES_TITLE)
            self.assertEqual((ax.get_xlabel(), ax.get_ylabel()), ("Outcome", "Validation runs"))
            self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ["Passed", "Failed", "Error"])
        self.assertEqual([round(p.get_height()) for p in wide.patches], [1, 1, 1])
        self.assertEqual([round(p.get_height()) for p in narrow.patches], [round(p.get_height()) for p in wide.patches])

    def test_both_drawings_use_the_design_tokens(self):
        self.assertEqual(charts.RUN_STATUS_COLORS, {"PASSED": TOKENS["pass"], "FAILED": TOKENS["fail"],
                                                    "ERROR": TOKENS["warn"]})
        self.assertEqual((charts.INK, charts.INK_SOFT, charts.GRID, charts.LINE_STRONG),
                         (TOKENS["ink"], TOKENS["ink_soft"], TOKENS["line"], TOKENS["line_strong"]))
        for layout in ("wide", "narrow"):
            ax = charts.build_run_outcomes_figure(layout).axes[0]
            with self.subTest(layout=layout):
                self.assertEqual([hex_colour(p.get_facecolor()) for p in ax.patches],
                                 [TOKENS["pass"], TOKENS["fail"], TOKENS["warn"]])
                self.assertEqual(hex_colour(ax.title.get_color()) if isinstance(ax.title.get_color(), tuple)
                                 else ax.title.get_color(), TOKENS["ink"])

    def test_the_narrow_legend_sits_above_the_plot(self):
        legend = charts.build_run_outcomes_figure("narrow").axes[0].get_legend()
        self.assertEqual(legend._ncols, 3)
        self.assertEqual(tuple(legend.get_bbox_to_anchor()._bbox.bounds[:2]), (0.5, 1.0))


class QualityHistoryPageTests(InsightData):
    def test_a_phone_gets_the_narrow_drawing_through_picture(self):
        html = self.html("data_quality:quality-history")
        picture = re.search(r"<picture>(.*?)</picture>", html, flags=re.S).group(1)
        self.assertIn('<source media="(max-width: 40em)" srcset="/quality/run-outcomes.png?layout=narrow 2x" '
                      'width="320" height="340">', picture)
        img = re.search(r"<img\b[^>]*>", picture).group(0)
        self.assertIn('src="/quality/run-outcomes.png"', img)
        self.assertIn('width="792" height="440"', img)
        self.assertIn("Passed: 1 run. Failed: 1 run. Error: 1 run.", img)

    def test_the_chart_and_its_text_equivalent_stay_side_by_side_in_one_grid(self):
        html = self.html("data_quality:quality-history")
        grid = html[html.index('<div class="insight-grid insight-grid--chart">'):]
        self.assertLess(grid.index("As a chart"), grid.index("The same numbers, as text"))
        self.assertIn('data-surface="insight"', html)

    def test_it_points_to_charts_and_reports(self):
        subtitle = self.html("data_quality:quality-history").split('<p class="page__subtitle">', 1)[1].split("</p>", 1)[0]
        self.assertIn(f'<a href="{reverse("data_quality:charts")}">Charts</a>', subtitle)
        self.assertIn(f'<a href="{reverse("data_quality:reports")}">Reports</a>', subtitle)


# --- Charts: the A4 Vega-Lite specs ----------------------------------------------------------

class VegaDesignTests(InsightData):
    def specs(self):
        return {n: json.loads(self.client.get(f"/vega-lite/chart{n}.json").content) for n in (1, 2)}

    def test_urls_data_urls_marks_and_fields_are_unchanged(self):
        specs = self.specs()
        self.assertEqual(specs[1]["data"], {"url": "/api/run-outcomes/"})
        self.assertEqual(specs[2]["data"], {"url": "/api/run-volume/"})
        self.assertEqual((specs[1]["mark"]["type"], specs[2]["mark"]["type"]), ("bar", "point"))
        self.assertEqual((specs[1]["encoding"]["x"]["field"], specs[1]["encoding"]["y"]["field"]), ("outcome", "runs"))
        self.assertEqual((specs[2]["encoding"]["x"]["field"], specs[2]["encoding"]["y"]["field"]),
                         ("rows_checked", "rows_failed"))
        for spec in specs.values():
            self.assertNotIn("values", spec["data"])

    def test_both_specs_carry_the_design_systems_config(self):
        for number, spec in self.specs().items():
            with self.subTest(chart=number):
                config = spec["config"]
                self.assertTrue(config["font"].startswith("Archivo,"))
                self.assertEqual(config["axis"]["labelColor"], TOKENS["ink_soft"])
                self.assertEqual(config["axis"]["titleColor"], TOKENS["ink"])
                self.assertEqual(config["axis"]["gridColor"], TOKENS["line"])
                self.assertEqual(config["axis"]["domainColor"], TOKENS["line_strong"])
                self.assertGreaterEqual(config["axis"]["labelFontSize"], 12)
                self.assertGreaterEqual(config["legend"]["labelFontSize"], 12)
                self.assertEqual((config["legend"]["orient"], config["legend"]["direction"],
                                  config["legend"]["titleOrient"]), ("top", "horizontal", "top"))
                # A Vega title never wraps: the subtitle is short lines, each narrow enough for a phone.
                lines = spec["title"]["subtitle"]
                self.assertIsInstance(lines, list)
                self.assertTrue(all(len(line) <= 34 for line in lines), lines)

    def test_outcome_colours_are_the_tokens_in_both_chart_systems(self):
        self.assertEqual(vega.OUTCOME_RANGE, [TOKENS["pass"], TOKENS["fail"], TOKENS["warn"]])
        self.assertEqual(vega.OUTCOME_RANGE, [charts.RUN_STATUS_COLORS[s] for s in ("PASSED", "FAILED", "ERROR")])
        for spec in self.specs().values():
            self.assertEqual(spec["encoding"]["color"]["scale"]["range"], vega.OUTCOME_RANGE)

    def test_the_scatter_shows_outcome_by_shape_as_well_as_colour(self):
        shape = self.specs()[2]["encoding"]["shape"]
        self.assertEqual((shape["field"], shape["title"]), ("outcome", "Outcome"))
        self.assertEqual(shape["scale"]["domain"], vega.OUTCOME_DOMAIN)
        self.assertEqual(len(set(shape["scale"]["range"])), 3)
        mark = self.specs()[2]["mark"]
        self.assertEqual((mark["type"], mark["filled"], mark["opacity"]), ("point", True, 1))


class ChartsPageWordingTests(InsightData):
    def test_no_developer_wording_and_questions_as_headings(self):
        html = self.html("data_quality:charts")
        main = html[html.index("<main"):html.index("</main>")]
        subtitle = main.split('<p class="page__subtitle">', 1)[1].split("</p>", 1)[0]
        self.assertNotIn("Vega-Lite", subtitle)
        self.assertNotIn("API", subtitle)
        self.assertNotIn("/api/", re.sub(r"<script\b.*?</script>", "", main, flags=re.S))
        self.assertEqual(re.findall(r'<h2 class="panel__title">([^<]+)</h2>', main),
                         ["How did the checked files turn out?", "Do bigger files fail more often?"])

    def test_spec_links_stay_as_footnotes_and_charts_are_described(self):
        html = self.html("data_quality:charts")
        for n in (1, 2):
            with self.subTest(chart=n):
                self.assertRegex(html, rf'<p class="chart__spec">\s*Chart specification:\s*'
                                       rf'<a href="/vega-lite/chart{n}.json">Vega-Lite JSON</a>')
                self.assertIn(f'aria-describedby="chart{n}-caption"', html)
                self.assertIn(f'<p class="insight-note" id="chart{n}-caption">', html)

    def test_the_charts_wait_for_archivo_and_draw_svg(self):
        html = self.html("data_quality:charts")
        self.assertIn('document.fonts.load("400 12px Archivo")', html)
        self.assertIn('renderer: "svg"', html)
        # vega-embed's icon-only "..." menu gets a name of its own once the chart is drawn.
        self.assertIn('menu.setAttribute("aria-label", "Chart options (save as an image, view the source, '
                      'open in the editor): "', html)
        for library in ("vega@5", "vega-lite@5", "vega-embed@6"):
            self.assertIn(f"https://cdn.jsdelivr.net/npm/{library}", html)


# --- Reports: the record and its exports -----------------------------------------------------

class ReportsRecordTests(InsightData):
    def test_totals_tables_and_exports_are_all_still_there(self):
        response = self.client.get(reverse("data_quality:reports"))
        self.assertEqual((response.context["dataset_total"], response.context["run_total"],
                          response.context["failed_total"]), (2, 3, 1))
        html = response.content.decode()
        for heading in ("Totals", "Runs by outcome", "Runs by dataset"):
            self.assertIn(f'<h2 class="panel__title">{heading}</h2>', html)
        self.assertIn(f'href="{reverse("data_quality:export-validation-runs-csv")}">Download CSV</a>', html)
        self.assertIn(f'href="{reverse("data_quality:export-validation-runs-json")}">Download JSON</a>', html)
        self.assertIn('<dl class="factlist factlist--stats">', html)
        self.assertIn("The exports hold every run, one row each, newest first.", html)

    def test_the_csv_export_holds_exactly_the_recorded_runs(self):
        response = self.client.get(reverse("data_quality:export-validation-runs-csv"))
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], ["id", "file_name", "dataset", "contract_version", "status", "submitted_by",
                                   "row_count", "started_at", "finished_at"])
        expected = [[str(r.id), r.file_name, r.contract.dataset.name, str(r.contract.version_number), r.status,
                     r.submitted_by.username if r.submitted_by else "", str(r.row_count), r.started_at.isoformat(),
                     r.finished_at.isoformat() if r.finished_at else ""]
                    for r in ValidationRun.objects.select_related("contract__dataset", "submitted_by").order_by("-started_at")]
        self.assertEqual(rows[1:], expected)

    def test_the_json_export_holds_exactly_the_recorded_runs(self):
        data = json.loads(self.client.get(reverse("data_quality:export-validation-runs-json")).content)
        self.assertEqual(set(data), {"generated_at", "record_count", "validation_runs"})
        self.assertEqual(data["record_count"], 3)
        self.assertEqual([(r["file_name"], r["dataset"], r["status"], r["row_count"]) for r in data["validation_runs"]],
                         [(r.file_name, r.contract.dataset.name, r.status, r.row_count)
                          for r in ValidationRun.objects.select_related("contract__dataset").order_by("-started_at")])


# --- No extra work per request ----------------------------------------------------------------

class InsightQueryTests(InsightData):
    """
    Query counts for a signed-in request, as measured before Stage 3E on the demo data
    (2 of each are the session and the user). Template changes must not add any.
    """
    EXPECTED = {
        "/quality/": 3, "/quality/run-outcomes.png": 3, "/quality/run-outcomes.png?layout=narrow": 3,
        "/charts/": 2, "/reports/": 7, "/vega-lite/chart1.json": 2, "/vega-lite/chart2.json": 2,
        "/reports/export/validation-runs.csv": 3, "/reports/export/validation-runs.json": 4,
    }

    def test_each_route_makes_the_same_number_of_queries_as_before(self):
        for url, count in self.EXPECTED.items():
            with self.subTest(url=url), self.assertNumQueries(count):
                self.assertEqual(self.client.get(url).status_code, 200)


# --- The stylesheet ---------------------------------------------------------------------------

class InsightStylesheetTests(StylesheetMixin, TestCase):
    def section(self):
        return self.css[self.css.index("/* ---- 23. insight pages"):]

    def test_the_frame_grid_and_phone_breakpoint(self):
        css = self.section()
        self.assertIn('.page[data-surface="insight"] { max-width: 1200px; }', css)
        self.assertRegex(css, r"@media \(min-width: 64\.0625em\) \{\s*\.insight-grid--chart \{ grid-template-columns: minmax\(0, 2fr\) minmax\(0, 1fr\); \}")
        self.assertIn(".chart-img { display: block; max-width: 100%; height: auto; margin: 0 auto; }", css)
        self.assertRegex(css, r"@media \(max-width: 40em\) \{\s*\.chart\.vega-embed\.has-actions \{ padding-right: 0; padding-top: 2\.25rem; \}")

    def test_nothing_moves_and_nothing_casts_a_shadow(self):
        css = re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S)
        for banned in ("box-shadow", "gradient"):
            self.assertNotIn(banned, css)
        # The one transition rule here switches vega-embed's menu fade off, and the
        # only animation is vega-embed's own menu entrance, tamed (see the next test).
        self.assertEqual(re.findall(r"transition:\s*([^;]+);", css), ["none"])
        self.assertEqual(re.findall(r"animation:\s*([^;]+);", css), ["chart-menu-in 150ms var(--ease-out)", "none"])

    def test_vega_embeds_menu_entrance_is_tamed_and_off_for_reduced_motion(self):
        css = self.section()
        keyframes = re.search(r"@keyframes chart-menu-in \{(.*?)\n\}", css, flags=re.S).group(1)
        self.assertEqual(set(re.findall(r"([a-z-]+):", keyframes)), {"opacity", "transform"})
        self.assertIn("scale(0.96)", keyframes)
        self.assertIn(".chart.vega-embed .vega-actions { transform-origin: top right; "
                      "animation: chart-menu-in 150ms var(--ease-out); }", css)
        self.assertRegex(css, r"@media \(prefers-reduced-motion: reduce\) \{\s*\.chart\.vega-embed \.vega-actions \{ animation: none; \}")

    def test_the_chart_menu_is_shown_plainly(self):
        self.assertIn(".chart.vega-embed details > summary { opacity: 1; transition: none; }", self.section())
