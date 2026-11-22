"""
UX Stage 3I - the AI Analytics page (/analytics/) in the product redesign.

What the redesign must not change, pinned against a fixed set of logged requests: the eleven charts
(chart IDs P1-P3, B1-B3, C1-C3 in their captions), each chart's inline data, every caption, every metric,
the filters and their fall-backs, the sign-in requirement and the number of queries.

What it changes, checked here: the 1200px frame, the summary of the filters applied, the section links,
the two different empty states, SVG charts drawn after Archivo loads with the shared CHART_CONFIG, named
chart menus, engine legends in the filter's words (colours frozen for A10), the cost-drivers table as
labelled blocks on a phone, and a stylesheet section with no motion and no fixed minimum width.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality.analytics import recorder
from data_quality.analytics.behavior import behavior_context
from data_quality.analytics.charts import ENGINE_DOMAIN, ENGINE_RANGE
from data_quality.analytics.cost import cost_context
from data_quality.analytics.performance import performance_context
from data_quality.analytics_views import filtered_logs
from data_quality.models import AIRequestLog
from data_quality.vega import CHART_CONFIG

URL = "/analytics/"
CSS = Path(settings.BASE_DIR) / "data_quality" / "static" / "data_quality" / "css" / "datapact.css"
BASE = datetime(2026, 10, 1, 12, 0, tzinfo=dt_timezone.utc)

CHART_IDS = ["latency-histogram", "latency-by-engine", "retrieval-vs-generation", "size-vs-latency",
             "requests-per-day", "requests-by-topic", "handbook-outcomes", "out-of-scope",
             "cost-by-model", "tokens-by-type", "cost-per-day"]
CAPTION_IDS = ["P1", "P2", "P3", "P3", "B1", "B2", "B3", "B3", "C1", "C2", "C3"]
ENGINE_LABELS_IN_FILTER = {"local": "Local model", "groq": "Groq API", "ollama": "Ollama (benchmark)"}

# Captured from the page as it was before Stage 3I (same fixture), so any change to what the page
# computes or says fails here. sha256 of json.dumps(..., sort_keys=True, default=str).
PINNED_DATA = {
    "latency-histogram": "e4dbd5e5e01c787870a46e0f30aed0c88f5dd1bb22d3d14973051d5c801ef8be",
    "latency-by-engine": "86058c40bd8a83bc973f106ac98aab1d1c38e5e31a5aad6d207290a3c1b36ba1",
    "retrieval-vs-generation": "12d4d37889b8f566a09518febf53a2759926aa16b49b605dd624b156a1c4c764",
    "size-vs-latency": "b94285b051aac46efaf90ca31f2027b57fff1ee92a0063b7dfcfd4a40f85cbe2",
    "requests-per-day": "dc6467189cf3dfc08792167eb8aa673067b64bc92b6794e9c1653fd9843b9ae7",
    "requests-by-topic": "842ab10a5a08b37a36c2b95ec53d1008557baac6d1cac361500b2a1f16e12a8a",
    "handbook-outcomes": "d1112a9b25d1d3b1336980d49bfea886e0450993a3fed9f086b3578755a4cb8d",
    "out-of-scope": "4827b16f123d8a1868dde19fda371ac81bfa4f772ff4fdf65321bba639117a55",
    "cost-by-model": "f3476a4709def5d3e8bff4dae8f0cc2f783f0d7a906c903269ad23bfcaf71167",
    "tokens-by-type": "0ae3316222bf293b6872fc7efe5fd46e3f04ed61abc47d7b9058857b1246bddc",
    "cost-per-day": "1f765cbd43289d777bd429b734b8c8f9a404f5bbe8b3312b8d674a1293fba2da",
}
PINNED_CAPTIONS = "253029d1672af0cc27141ceaaf936c8374dbe77a88f0cb7db4b82d2b8103a35f"
PINNED_METRICS = {
    "performance": "4992cb608cfdd73b95b07a579f0317be9156e79a872989fff394e72141a28665",
    "behavior": "53352b1e27791c7ea9db94490020121564845e4356b1c3d30362109ca3520b8e",
    "cost": "a6ff0a992530c54f0f2e3aef5e9336da1947c368cc5cf0ade32b1434ba06959d",
}
PINNED_DRIVERS = "380c22db3e606417e48dde3a7134520955c2f7531dc0db06be39279729109e10"
PINNED_QUERIES = 18


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def log(minutes, **fields):
    values = dict(feature="explain", engine="groq", model_name="openai/gpt-oss-20b", status="ok",
                  latency_ms=900, prompt_tokens=700, completion_tokens=250, query_type="REGEX",
                  input_chars=1700, source="benchmark")
    values.update(fields)
    return recorder.record(values.pop("feature"), values.pop("engine"), values.pop("model_name"),
                           created_at=BASE - timedelta(minutes=minutes), **values)


def build_logs():
    """A fixed mix: three engines, both features, every outcome, two sources, five weeks."""
    rows = [
        dict(),
        dict(engine="groq", latency_ms=420, query_type="RANGE"),
        dict(engine="local", model_name="HuggingFaceTB/SmolLM2-1.7B-Instruct", latency_ms=9100),
        dict(engine="ollama", model_name="smollm2:1.7b", latency_ms=2600, query_type="ALLOWED_VALUES"),
        dict(engine="ollama", model_name="qwen2.5:14b", latency_ms=3900, query_type="TYPE_MATCH"),
        dict(feature="handbook", engine="groq", query_type="rules", input_chars=48, retrieval_ms=6, latency_ms=640),
        dict(feature="handbook", engine="local", model_name="HuggingFaceTB/SmolLM2-1.7B-Instruct",
             query_type="contracts", input_chars=61, retrieval_ms=5, latency_ms=24000),
        dict(feature="handbook", engine="ollama", model_name="smollm2:1.7b", query_type="runs",
             input_chars=35, retrieval_ms=93, latency_ms=3100, status="not_found"),
        dict(feature="handbook", engine="ollama", model_name="qwen2.5:14b", query_type="out_of_scope",
             input_chars=40, retrieval_ms=5, latency_ms=5, status="no_passages", prompt_tokens=0,
             completion_tokens=0),
        dict(feature="handbook", engine="groq", query_type="out_of_scope", input_chars=52, retrieval_ms=4,
             latency_ms=700, status="ok"),
        dict(feature="handbook", engine="local", model_name="HuggingFaceTB/SmolLM2-1.7B-Instruct",
             query_type="out_of_scope", input_chars=44, retrieval_ms=5, latency_ms=14000, status="not_found"),
        dict(feature="handbook", engine="groq", query_type="violations", input_chars=70, retrieval_ms=7,
             latency_ms=810, status="invalid"),
        dict(engine="local", model_name="HuggingFaceTB/SmolLM2-1.7B-Instruct", latency_ms=30, status="error",
             prompt_tokens=0, completion_tokens=0),
        dict(engine="groq", latency_ms=500, source="simulated"),
    ]
    for index, fields in enumerate(rows):
        log(index * 2017, **fields)  # about 1.4 days apart, so the rows spread over three weeks


def sections(qs):
    return performance_context(qs), behavior_context(qs), cost_context(qs)


class AnalyticsData(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("analyst", password="pw-analyst-3i")
        build_logs()

    def get(self, query=""):
        self.client.force_login(self.user)
        return self.client.get(URL + query)

    def html(self, query=""):
        return self.get(query).content.decode()


# --- What must not change -----------------------------------------------------------------------

class AnalyticalIntegrityTests(AnalyticsData):
    def charts(self, params=None):
        qs, _ = filtered_logs(params or {"days": "all"})
        return [chart for ctx in sections(qs) for chart in ctx["charts"]]

    def test_the_eleven_charts_and_nine_chart_ids_are_all_there_in_order(self):
        charts = self.charts()
        self.assertEqual([chart["id"] for chart in charts], CHART_IDS)
        self.assertEqual([chart["caption"][:2] for chart in charts], CAPTION_IDS)
        self.assertEqual(sorted(set(CAPTION_IDS)), ["B1", "B2", "B3", "C1", "C2", "C3", "P1", "P2", "P3"])

    def test_every_charts_data_is_unchanged(self):
        self.assertEqual({chart["id"]: sha(chart["spec"]["data"]["values"]) for chart in self.charts()}, PINNED_DATA)

    def test_every_caption_and_title_is_unchanged(self):
        self.assertEqual(sha([(chart["id"], chart["title"], chart["caption"], chart["wide"]) for chart in self.charts()]),
                         PINNED_CAPTIONS)

    def test_every_metric_is_unchanged(self):
        qs, _ = filtered_logs({"days": "all"})
        metrics = {name: sha({k: v for k, v in ctx.items() if k != "charts"})
                   for name, ctx in zip(("performance", "behavior", "cost"), sections(qs))}
        self.assertEqual(metrics, PINNED_METRICS)

    def test_the_cost_drivers_are_unchanged(self):
        qs, _ = filtered_logs({"days": "all"})
        self.assertEqual(sha(cost_context(qs)["drivers"]), PINNED_DRIVERS)

    def test_the_filters_and_their_fall_backs_are_unchanged(self):
        self.assertEqual(filtered_logs({})[1], {"days": "30", "engine": "", "source": ""})
        self.assertEqual(filtered_logs({"days": "bogus", "engine": "bogus", "source": "bogus"})[1],
                         {"days": "30", "engine": "", "source": ""})
        self.assertEqual(filtered_logs({"days": "all"})[0].count(), 14)
        self.assertEqual(filtered_logs({"days": "all", "engine": "groq"})[0].count(), 6)
        self.assertEqual(filtered_logs({"days": "all", "source": "simulated"})[0].count(), 1)
        self.assertEqual(filtered_logs({"days": "all", "source": "live"})[0].count(), 0)
        # Counted back from the newest row: the 7-day window holds the five newest rows.
        self.assertEqual(filtered_logs({"days": "7"})[0].count(), 5)

    def test_the_engine_colours_are_frozen_for_a10(self):
        self.assertEqual(ENGINE_DOMAIN, ["local", "groq", "ollama"])
        self.assertEqual(ENGINE_RANGE, ["#2f5d8a", "#c2662d", "#6b8f3a"])
        for chart in self.charts():
            color = chart["spec"]["encoding"].get("color", {})
            if color.get("field") == "engine":
                self.assertEqual(color["scale"], {"domain": ENGINE_DOMAIN, "range": ENGINE_RANGE})

    def test_the_page_makes_no_extra_queries(self):
        self.client.force_login(self.user)
        with self.assertNumQueries(PINNED_QUERIES):
            self.client.get(URL + "?days=all")

    def test_sign_in_is_still_required(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("data_quality:login"), response["Location"])


# --- Chart presentation --------------------------------------------------------------------------

class ChartPresentationTests(AnalyticsData):
    def charts(self):
        qs, _ = filtered_logs({"days": "all"})
        return [chart for ctx in sections(qs) for chart in ctx["charts"]]

    def test_every_chart_uses_the_shared_chart_config(self):
        for chart in self.charts():
            config = chart["spec"]["config"]
            for key, value in CHART_CONFIG.items():
                self.assertEqual(config[key], value, f"{chart['id']}: {key}")

    def test_engine_legends_use_the_filters_words(self):
        engine_charts = [c for c in self.charts() if c["spec"]["encoding"].get("color", {}).get("field") == "engine"]
        self.assertEqual([c["id"] for c in engine_charts],
                         ["latency-histogram", "size-vs-latency", "cost-by-model", "cost-per-day"])
        self.assertEqual(dict(AIRequestLog.Engine.choices), ENGINE_LABELS_IN_FILTER)
        for chart in engine_charts:
            expr = chart["spec"]["encoding"]["color"]["legend"]["labelExpr"]
            for value, label in ENGINE_LABELS_IN_FILTER.items():
                self.assertIn(f"datum.value === '{value}' ? '{label}'", expr)

    def test_charts_render_as_svg_after_archivo_loads(self):
        html = self.html("?days=all")
        script = html[html.rindex("<script>"):]
        self.assertIn('var EMBED = {renderer: "svg", actions:', script)
        self.assertIn('document.fonts.load("400 12px Archivo")', script)
        # Every chart is drawn only once the font promise settles.
        self.assertRegex(script, r'fontsReady\.then\(function \(\) \{\s*document\.querySelectorAll\("\.vega-chart"\)'
                                 r'\.forEach\(function \(el\) \{\s*draw\(el\)')
        self.assertEqual(script.count("vegaEmbed(el, steps[i](fit), EMBED)"), 1)

    def test_a_legend_that_runs_past_the_edge_is_redrawn_not_cut(self):
        # In order: as built; one legend entry per line; long entries over several lines.
        # Never a label limit (which would cut words off) and never a smaller font.
        script = self.html("?days=all").rsplit("<script>", 1)[1]
        self.assertIn("function () { return onePerLine(base(JSON.parse(source))); }", script)
        self.assertIn("function (fit) { return wrapLegend(onePerLine(base(JSON.parse(source))), fit); }", script)
        self.assertIn('{direction: "vertical", labelLimit: 0}', script)
        self.assertNotRegex(script, r"labelLimit:\s*[1-9]")
        self.assertNotRegex(script, r"(label|title)FontSize")
        # The menu keeps what it offered before: save as an image and view the source.
        self.assertIn("actions: {export: true, source: true, editor: false, compiled: false}", script)

    def test_phone_x_axis_keeps_end_labels_inside_the_drawing(self):
        # Stage 3I correction: labelFlush: true only flushed a label sitting exactly on the
        # plot's edge; the median-time chart's log scale has 18px of padding, so its last
        # tick label ran past the edge on a phone when filtered to one engine. A 24px
        # threshold keeps it inside. No label limit, no hidden labels, no smaller text.
        script = self.html("?days=all").rsplit("<script>", 1)[1]
        narrow = script[script.index("function narrow(spec) {"):]
        narrow = narrow[:narrow.index("return spec;")]
        self.assertIn("spec.config.axisX = Object.assign({}, spec.config.axisX, {tickCount: 4, labelFlush: 24});", narrow)
        self.assertNotIn("labelFlush: true", script)
        self.assertNotRegex(narrow, r"labelBound|labelOverlap|labelLimit:\s*[1-9]")

    def test_every_chart_menu_gets_a_name_with_its_charts_title(self):
        script = self.html("?days=all").rsplit("<script>", 1)[1]
        self.assertIn('menu.setAttribute("aria-label", "Chart options (save as an image or view the source): "', script)
        self.assertIn('el.closest(".panel").querySelector(".panel__title")', script)

    def test_eleven_charts_each_with_its_spec_and_a_fallback(self):
        html = self.html("?days=all")
        for chart_id in CHART_IDS:
            self.assertIn(f'<div class="chart vega-chart" id="chart-{chart_id}" data-spec-id="spec-{chart_id}">', html)
            self.assertIn(f'<script id="spec-{chart_id}" type="application/json">', html)
        self.assertEqual(html.count('class="chart vega-chart"'), 11)
        self.assertEqual(html.count("This chart needs JavaScript and the Vega-Lite library."), 11)

    def test_the_vega_libraries_are_unchanged(self):
        html = self.html("?days=all")
        for library in ("vega@5", "vega-lite@5", "vega-embed@6"):
            self.assertIn(f'<script src="https://cdn.jsdelivr.net/npm/{library}"></script>', html)


# --- Page structure ------------------------------------------------------------------------------

class PageStructureTests(AnalyticsData):
    def test_the_wide_frame_and_one_heading(self):
        html = self.html()
        self.assertIn('<main class="page" id="main" data-surface="analytics">', html)
        self.assertEqual(html.count("<h1"), 1)
        self.assertIn("AI Analytics", html)

    def test_no_inline_styles_or_page_stylesheet(self):
        html = self.html("?days=all")
        main = html[html.index("<main"):html.index("</main>")]
        self.assertNotIn(" style=", main)
        self.assertNotIn("<style>", html)

    def test_the_applied_filters_are_summarised(self):
        html = self.html("?days=7&engine=groq&source=benchmark")
        summary = html[html.index('<dl class="factlist analytics-applied">'):]
        summary = summary[:summary.index("</dl>")]
        for text in ("Showing", "2 of 14 logged requests", "Time range", "Last 7 days", "Engine", "Groq API",
                     "Data source", "Benchmark run"):
            self.assertIn(text, summary)
        defaults = self.html()
        defaults = defaults[defaults.index('<dl class="factlist analytics-applied">'):]
        for text in ("Last 30 days", "All engines", "All sources"):
            self.assertIn(text, defaults[:defaults.index("</dl>")])

    def test_the_filters_keep_their_names_labels_and_choices(self):
        html = self.html("?days=bogus&engine=bogus&source=bogus")
        self.assertIn('<form method="get" class="analytics__filters" aria-label="Filter the dashboard">', html)
        for field, label in (("days", "Time range"), ("engine", "Engine"), ("source", "Data source")):
            self.assertIn(f'<label for="f-{field}">{label}</label>', html)
            self.assertIn(f'<select id="f-{field}" name="{field}">', html)
        self.assertIn('<option value="30" selected>Last 30 days</option>', html)
        self.assertIn('<option value="" selected>All engines</option>', html)
        self.assertIn('<option value="" selected>All sources</option>', html)
        self.assertIn('<button type="submit" class="btn btn--primary btn--sm">Apply</button>', html)

    def test_section_links_point_at_the_three_sections(self):
        html = self.html("?days=all")
        nav = html[html.index('<nav class="analytics-jump" aria-label="Dashboard sections">'):]
        nav = nav[:nav.index("</nav>")]
        links = re.findall(r'<a href="#([a-z]+)">([^<]+)</a>', nav)
        self.assertEqual(links, [("performance", "System performance"), ("behavior", "User behavior"), ("cost", "Cost")])
        for target, heading in links:
            self.assertIn(f'<section class="analytics__section" id="{target}" aria-labelledby="sec-{target}">', html)
            self.assertIn(f'<h2 id="sec-{target}">{heading}</h2>', html)
        self.assertIn("4 charts", nav)
        self.assertIn("3 charts and a table", nav)
        order = [html.index(f'id="{target}"') for target, _ in links]
        self.assertEqual(order, sorted(order))
        self.assertLess(html.index('class="analytics-jump"'), order[0])

    def test_cost_drivers_table_has_row_headers_labels_and_a_caption(self):
        html = self.html("?days=all")
        table = html[html.index('<table class="datatable dtable dtable--drivers" role="table">'):]
        table = table[:table.index("</table>")]
        self.assertIn('<caption class="visually-hidden">', table)
        headers = re.findall(r'<th scope="col" role="columnheader"[^>]*>([^<]+)</th>', table)
        self.assertEqual(headers, ["Feature / type", "Engine", "Requests", "Avg tokens", "Total cost", "Share of cost"])
        body = table[table.index("<tbody"):]
        rows = body.count('<tr role="row">')
        self.assertGreater(rows, 0)
        self.assertEqual(body.count('<th scope="row" role="rowheader" data-label="Feature / type">'), rows)
        for label in headers[1:]:
            self.assertEqual(body.count(f'data-label="{label}"'), rows, label)
        self.assertIn("C2. Where the money goes", html)


class EmptyStateTests(AnalyticsData):
    def test_filters_that_match_nothing_say_so_and_offer_a_reset(self):
        html = self.html("?source=live")
        self.assertIn("No requests match these filters.", html)
        self.assertIn("14 requests are logged, but none match this time range, engine and data source.", html)
        self.assertIn(f'<a class="btn btn--primary" href="{URL}">Reset filters</a>', html)
        self.assertNotIn("No AI requests logged yet.", html)
        self.assertNotIn('class="analytics-jump"', html)
        self.assertNotIn('class="analytics__section"', html)

    def test_an_empty_log_keeps_its_exact_sentence(self):
        AIRequestLog.objects.all().delete()
        html = self.html()
        self.assertIn('<p class="empty-state__headline">No AI requests logged yet.</p>', html)
        self.assertIn("Use Explain with AI or the Handbook, or load data/ai_logs.csv with manage.py load_ai_logs.", html)
        self.assertNotIn("No requests match these filters.", html)
        self.assertNotIn("Reset filters", html)


# --- Stylesheet ----------------------------------------------------------------------------------

class AnalyticsStylesheetTests(TestCase):
    def section(self):
        css = CSS.read_text(encoding="utf-8")
        return css[css.index("/* ---- 26. AI analytics"):]

    def test_the_wide_frame_and_a_grid_no_wider_than_its_column(self):
        css = self.section()
        self.assertIn('.page[data-surface="analytics"] { max-width: 1200px; }', css)
        self.assertIn(".analytics__grid { display: grid; grid-template-columns: minmax(0, 1fr);", css)
        self.assertRegex(css, r"@media \(min-width: 64\.0625em\) \{\s*\.analytics__grid \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}")
        # No column or chart may demand more width than a 320px phone has.
        rules = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        self.assertNotRegex(rules, r"minmax\(\s*[1-9]\d*px")
        self.assertNotIn("420px", rules)

    def test_the_drivers_table_reflows_on_a_phone_without_hiding_anything(self):
        css = self.section()
        phone = css[css.index("@media (max-width: 40em)"):]
        self.assertIn('.dtable--drivers th[scope="row"] { grid-column: 1 / -1; }', phone)
        self.assertNotRegex(phone, r"display:\s*none")

    def test_nothing_moves(self):
        css = re.sub(r"/\*.*?\*/", "", self.section(), flags=re.S)
        for banned in ("animation", "transition", "box-shadow", "gradient", "@keyframes", "scroll-behavior: smooth"):
            self.assertNotIn(banned, css)
        self.assertNotRegex(css, r"(?<!text-)transform")
