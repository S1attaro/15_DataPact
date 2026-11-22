"""
Product redesign, Stage 3B - the application shell and its navigation.
Author: Tejas Jaggi (with Claude Code).

What these tests pin down:

  - signed in, every page sits in the application shell (.shell--app);
    signed out, the plain top bar is unchanged and shows no groups;
  - the navigation offers exactly the existing destinations, each once,
    each one loading, in three labelled groups (Data, Quality, AI);
  - every destination marks its own link, and only that one, as the
    current page (aria-current), and pages outside the navigation (a
    dataset, a violation) mark nothing;
  - the planned Upload item stays in the Data group, as text, not a link;
  - the stylesheet hands the navigation from the Menu button to the
    sidebar at one em breakpoint, with no gap or overlap between them, and
    marks the active page with a shape as well as colour.

The shell was also checked in a browser at 1440, 1024, 768 and 390 px
(docs/redesign/shell/after/).
"""

import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from data_quality.models import Dataset
from data_quality.tests import SignedInClientMixin, StylesheetMixin

# (route name, link label, group) in the order the navigation shows them.
NAV = (
    ("data_quality:home", "Home", None),
    # Stage 3C: Overview is the workspace overview, beside Home, outside the groups.
    ("data_quality:dataset-cbv-base", "Overview", None),
    ("data_quality:dataset-list", "Datasets", "Data"),
    ("data_quality:contract-search", "Contracts", "Data"),
    ("data_quality:dataset-manage", "Manage", "Data"),
    ("data_quality:quality-history", "Quality History", "Quality"),
    ("data_quality:charts", "Charts", "Quality"),
    ("data_quality:reports", "Reports", "Quality"),
    ("data_quality:analytics", "AI Analytics", "AI"),
    ("data_quality:handbook-ask", "Handbook", "AI"),
)


def header(html):
    return html[html.index('<header class="topbar">'):html.index("</header>")]


def nav(html):
    bar = header(html)
    return bar[bar.index('<nav class="mainnav"'):bar.index("</nav>")]


def groups(nav_html):
    """{group label: [link labels and planned items, in order]}."""
    found = {}
    for block in re.findall(r'<div class="mainnav__group".*?</div>', nav_html, flags=re.S):
        label = re.search(r'<p class="mainnav__heading" id="[^"]+"[^>]*>([^<]+)</p>', block).group(1)
        # A link's own text, before any status tag inside it (Stage 3B.1).
        items = [t.strip() for t in re.findall(r'<a href="[^"]+"(?: class="is-active" aria-current="page")?>([^<]+)', block)]
        if 'class="mainnav__planned"' in block:
            items.append("Upload")
        found[label] = items
    return found


class ShellWrapperTests(SignedInClientMixin, TestCase):
    def test_signed_in_pages_sit_in_the_application_shell(self):
        for name in ("data_quality:home", "data_quality:dataset-list", "data_quality:analytics"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('<div class="shell shell--app">', html)
                # The shell wraps the header, the page and the footer.
                self.assertLess(html.index('<div class="shell shell--app">'), html.index('<header class="topbar">'))
                self.assertLess(html.index("</footer>"), html.rindex("</div>"))

    def test_signed_out_the_shell_is_the_plain_top_bar(self):
        self.client.logout()
        for name in ("data_quality:home", "data_quality:login", "data_quality:signup"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('<div class="shell">', html)
                self.assertNotIn("shell--app", html)
                self.assertNotIn("mainnav__group", html)


class NavigationContentTests(SignedInClientMixin, TestCase):
    def setUp(self):
        self.nav = nav(self.client.get(reverse("data_quality:home")).content.decode())

    def test_every_destination_is_offered_once_and_loads(self):
        hrefs = re.findall(r'<a href="([^"]+)"', self.nav)
        self.assertEqual(hrefs, [reverse(name) for name, _, _ in NAV])
        self.assertEqual(len(hrefs), len(set(hrefs)))
        for href in hrefs:
            with self.subTest(href=href):
                self.assertEqual(self.client.get(href).status_code, 200)

    def test_the_destinations_are_grouped_by_the_job_they_serve(self):
        expected = {}
        for _, label, group in NAV:
            if group:
                expected.setdefault(group, []).append(label)
        expected["Data"].append("Upload")
        self.assertEqual(groups(self.nav), expected)

    def test_each_group_is_a_labelled_group_whose_label_exists(self):
        for match in re.finditer(r'<div class="mainnav__group" role="group" aria-labelledby="([^"]+)">', self.nav):
            with self.subTest(group=match.group(1)):
                self.assertIn(f'id="{match.group(1)}"', self.nav)
        self.assertEqual(self.nav.count('role="group"'), 3)

    def test_group_labels_are_not_headings(self):
        # The page's own h1 stays the first heading a screen reader lists.
        self.assertNotRegex(self.nav, r"<h[1-6]")

    def test_upload_stays_a_planned_item_in_the_data_group(self):
        data = re.search(r'aria-labelledby="nav-group-data">.*?</div>', self.nav, flags=re.S).group(0)
        self.assertIn('<span class="mainnav__planned">Upload', data)
        self.assertNotRegex(data, r"<a [^>]*>\s*Upload")


class ActivePageTests(SignedInClientMixin, TestCase):
    def test_every_destination_marks_only_its_own_link(self):
        for name, label, _ in NAV:
            with self.subTest(page=name):
                html = nav(self.client.get(reverse(name)).content.decode())
                self.assertEqual(html.count('aria-current="page"'), 1)
                # The link's text, then either its end or a status tag (Handbook, Stage 3B.1).
                self.assertRegex(html, rf'<a href="{re.escape(reverse(name))}" class="is-active" aria-current="page">'
                                       rf'{re.escape(label)}(?:</a>| <span class="mainnav__tag">)')

    def test_pages_outside_the_navigation_mark_nothing(self):
        owner = User.objects.create_user("owner_shell", password="pw")
        dataset = Dataset.objects.create(name="Weekly Sales Extract", owner=owner, source_team="Finance")
        html = self.client.get(reverse("data_quality:dataset-detail", args=[dataset.pk])).content.decode()
        self.assertNotIn("aria-current", header(html))
        self.assertIn('<div class="shell shell--app">', html)


class ShellStyleTests(StylesheetMixin, TestCase):
    def shell_css(self):
        return self.css[self.css.index("20. application shell"):]

    def test_the_menu_and_the_sidebar_meet_at_one_breakpoint(self):
        fold = re.findall(r"@media \(max-width: ([\d.]+)em\) \{\s*/\* Stage 3B", self.css)
        side = re.findall(r"@media \(min-width: ([\d.]+)em\) \{\s*\.shell--app \{", self.shell_css())
        self.assertEqual(len(fold), 1, "no Stage 3B fold block")
        self.assertEqual(len(side), 1, "no sidebar block")
        # The fold ends a sixteenth of a pixel before the sidebar starts.
        self.assertAlmostEqual(float(side[0]) - float(fold[0]), 0.0625, places=4)

    def test_the_sidebar_stays_in_view_and_scrolls_on_its_own(self):
        rule = re.search(r"\.shell--app > \.topbar \{([^}]*)\}", self.shell_css()).group(1)
        for declaration in (r"position:\s*sticky", r"top:\s*0", r"height:\s*100vh", r"overflow-y:\s*auto"):
            with self.subTest(declaration=declaration):
                self.assertRegex(rule, declaration)

    def test_the_active_page_has_a_shape_not_only_a_colour(self):
        css = self.shell_css()
        self.assertRegex(css, r"\.shell--app \.mainnav a::before,[^{]*\{[^}]*border-radius:\s*50%")
        self.assertRegex(css, r"\.shell--app \.mainnav a\.is-active::before \{[^}]*background:")
        self.assertRegex(css, r"\.shell--app \.mainnav a\.is-active \{[^}]*font-weight:\s*600")

    def test_navigation_hover_needs_a_real_pointer(self):
        css = self.shell_css()
        hovers = re.findall(r"(?m)^\s*([^{}\n]*:hover[^{}\n]*)\{", css)
        gated = css[css.index("@media (hover: hover) and (pointer: fine)"):]
        self.assertTrue(hovers)
        for selector in hovers:
            with self.subTest(selector=selector):
                self.assertIn(selector.strip(), gated)


# ---------------------------------------------------------------------------
# Stage 3B.1: navigation polish
# ---------------------------------------------------------------------------

from unittest import mock  # noqa: E402

from django.test import override_settings  # noqa: E402

STATUS = "data_quality.templatetags.navigation.retrieval.handbook_status"


def handbook_link(nav_html):
    return re.search(r'<a href="/handbook/"[^>]*>.*?</a>', nav_html, flags=re.S).group(0)


class HandbookLabelTests(SignedInClientMixin, TestCase):
    """The Handbook link says when this server cannot answer, from the real check."""

    def link(self):
        return handbook_link(nav(self.client.get(reverse("data_quality:reports")).content.decode()))

    @override_settings(AI_LOCAL_ENABLED=False)
    def test_with_the_local_model_off_it_says_local_only(self):
        # The production setting (settings/production.py defaults it off).
        link = self.link()
        self.assertIn('<span class="mainnav__tag">Local only<span class="visually-hidden">, '
                      'not available on this server</span></span>', link)

    def test_where_the_handbook_works_there_is_no_label(self):
        with mock.patch(STATUS, return_value=None):
            self.assertEqual(self.link(), '<a href="/handbook/">Handbook</a>')

    def test_switched_on_but_not_configured_it_says_not_set_up(self):
        for reason in ("not_configured", "missing_kb"):
            with self.subTest(reason=reason), mock.patch(STATUS, return_value=reason):
                self.assertIn('<span class="mainnav__tag">Not set up<span class="visually-hidden">', self.link())

    def test_the_label_follows_the_same_check_as_the_handbook_page(self):
        for enabled in (True, False):
            with self.subTest(AI_LOCAL_ENABLED=enabled), override_settings(AI_LOCAL_ENABLED=enabled):
                response = self.client.get(reverse("data_quality:handbook-ask"))
                page_status = response.context["status"]
                link = handbook_link(nav(response.content.decode()))
                self.assertEqual("mainnav__tag" in link, page_status is not None)

    def test_the_link_and_the_upload_label_are_unchanged(self):
        with mock.patch(STATUS, return_value="off"):
            html = nav(self.client.get(reverse("data_quality:reports")).content.decode())
        self.assertIn('href="/handbook/"', html)
        self.assertIn('<span class="mainnav__planned">Upload <span class="mainnav__tag">Not'
                      '<span class="visually-hidden"> available</span> yet</span></span>', html)


class GroupLabelAnnouncementTests(SignedInClientMixin, TestCase):
    def test_each_group_keeps_its_name_and_its_label_is_not_read_twice(self):
        html = nav(self.client.get(reverse("data_quality:home")).content.decode())
        for group, label in (("data", "Data"), ("quality", "Quality"), ("ai", "AI")):
            with self.subTest(group=group):
                self.assertIn(f'role="group" aria-labelledby="nav-group-{group}"', html)
                self.assertIn(f'<p class="mainnav__heading" id="nav-group-{group}" aria-hidden="true">{label}</p>', html)
        # Only the three labels are hidden; no link is.
        self.assertEqual(html.count('aria-hidden="true"'), 3)
        self.assertNotRegex(html, r'<a [^>]*aria-hidden')


class NoPillShapeTests(StylesheetMixin, TestCase):
    def test_the_status_tag_is_a_square_stamp(self):
        rule = self.rule(".mainnav__tag")
        self.assertRegex(rule, r"border-radius:\s*var\(--radius\)")
        self.assertRegex(rule, r"border:\s*1px dashed")

    def test_no_pill_radius_and_no_unused_view_caption_remain(self):
        self.assertNotIn("999px", self.css)
        self.assertNotRegex(self.css, r"(?m)^\.viewchip")


class WrappedLabelAlignmentTests(StylesheetMixin, TestCase):
    """
    Stage 3B.2: in the Menu (below 80em) a status label that wraps under its
    link starts under the link's text, not under the active dot. The dot sits
    in the row's left padding, and that padding equals the group labels'
    indent, so labels, link text and wrapped status labels share one edge.
    """

    def fold_block(self):
        start = self.css.index("@media (max-width: 79.9375em) {")
        return self.css[start:self.css.index("@media (max-width: 38.75em)", start)]

    def test_the_dot_sits_in_the_rows_left_padding(self):
        css = self.fold_block()
        row = re.search(r"\.topbar\.has-menutoggle \.mainnav a,\s*\.topbar\.has-menutoggle \.mainnav__planned \{([^}]*)\}", css).group(1)
        self.assertRegex(row, r"position:\s*relative")
        self.assertRegex(row, r"padding:\s*0\.55rem 0\.6rem 0\.55rem 1\.7rem")
        dot = re.search(r"\.topbar\.has-menutoggle \.mainnav a::before,\s*\.topbar\.has-menutoggle \.mainnav__planned::before \{([^}]*)\}", css).group(1)
        self.assertRegex(dot, r"position:\s*absolute")
        self.assertRegex(dot, r"left:\s*0\.6rem")

    def test_rows_and_group_labels_share_one_left_edge(self):
        css = self.fold_block()
        heading = re.search(r"\.topbar\.has-menutoggle \.mainnav__heading \{([^}]*)\}", css).group(1)
        self.assertRegex(heading, r"padding:\s*0\.75rem 0\.6rem 0\.25rem 1\.7rem")

    def test_both_status_labels_drop_their_side_margin_in_the_menu(self):
        self.assertRegex(
            self.fold_block(),
            r"\.topbar\.has-menutoggle \.mainnav a \.mainnav__tag,\s*\.topbar\.has-menutoggle \.mainnav__planned \.mainnav__tag \{\s*margin-left:\s*0;",
        )
