"""
UX Stage 5 - navigation, keyboard access, contrast and small screens.
Author: Tejas Jaggi.

What these tests pin down, each found in a browser audit of the live pages:

  - a "Skip to main content" link comes first on every page, so a keyboard
    user does not Tab through the whole top bar to reach the page;
  - the top navigation is a labelled landmark and marks the current page
    for screen readers (aria-current), not only with a colour;
  - the "Upload" item, which is not built yet, says so in visible text
    instead of a hover tooltip, and is readable on the dark bar;
  - signed in, a "Menu" button folds the navigation away on narrow screens
    and at high zoom; the page script only adds it, so without the script
    the bar stays as it was;
  - text and field-border colours meet WCAG AA contrast, and every
    keyboard focus gets a visible ring, including on the dark top bar;
  - the top bar's breakpoints are in em, so they follow the browser's text
    size as well as its zoom.

The test runner has no browser, so the CSS checks read the stylesheet; the
rendered pages were also checked in a browser (see the PR notes).
"""

import re

from django.test import TestCase
from django.urls import reverse

from data_quality.models import Dataset
from data_quality.tests import SignedInClientMixin, StylesheetMixin, contrast_ratio


def topbar(html):
    return html[html.index('<header class="topbar">'):html.index("</header>")]


def text_of(html):
    """The text a reader gets: tags removed, whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


class SkipLinkTests(SignedInClientMixin, TestCase):
    PAGES = ("data_quality:home", "data_quality:dataset-list", "data_quality:contract-search")

    def first_control(self, html):
        body = html[html.index("<body>"):]
        return re.search(r"<(?:a|button)\b[^>]*>[^<]*", body).group(0)

    def test_the_first_link_on_every_page_skips_to_the_main_content(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                first = self.first_control(html)
                self.assertIn('class="skiplink"', first)
                self.assertIn('href="#main"', first)
                self.assertTrue(first.endswith("Skip to main content"), first)
                self.assertRegex(html, r'<main class="page" id="main"[ >]')

    def test_signed_out_pages_have_it_too(self):
        self.client.logout()
        for name in ("data_quality:home", "data_quality:login"):
            with self.subTest(page=name):
                html = self.client.get(reverse(name)).content.decode()
                self.assertIn('href="#main"', self.first_control(html))


class NavigationSemanticsTests(SignedInClientMixin, TestCase):
    def nav(self, name):
        html = topbar(self.client.get(reverse(name)).content.decode())
        return html[html.index("<nav"):html.index("</nav>")]

    def test_the_navigation_is_a_labelled_landmark(self):
        self.assertRegex(self.nav("data_quality:home"), r'^<nav class="mainnav" aria-label="Main">')

    def test_the_current_page_is_named_for_screen_readers(self):
        nav = self.nav("data_quality:dataset-list")
        self.assertEqual(nav.count('aria-current="page"'), 1)
        self.assertRegex(nav, r'<a href="[^"]+" class="is-active" aria-current="page">Datasets</a>')

    def test_a_page_outside_the_navigation_marks_nothing_current(self):
        # A dataset's own page has no item of its own in the navigation.
        dataset = Dataset.objects.create(name="Weekly Sales Extract", owner=self.signed_in_user, source_team="Finance")
        html = self.client.get(reverse("data_quality:dataset-detail", args=[dataset.pk])).content.decode()
        self.assertNotIn("aria-current", topbar(html))

    def test_upload_says_in_visible_text_that_it_is_not_available(self):
        nav = self.nav("data_quality:home")
        item = re.search(r'<span class="mainnav__planned">.*?</span>\s*</span>', nav, re.S)
        self.assertIsNotNone(item, "no planned Upload item")
        self.assertEqual(text_of(item.group(0)), "Upload Not available yet")
        # The short visible tag; " available" is for screen readers.
        self.assertIn('<span class="mainnav__tag">Not<span class="visually-hidden"> available</span> yet</span>', nav)
        self.assertNotIn("title=", nav)
        self.assertNotIn("wireframe", nav.lower())
        self.assertNotRegex(nav, r"<a [^>]*>\s*Upload")


class MenuToggleTests(SignedInClientMixin, TestCase):
    BUTTON = (
        '<button type="button" class="btn btn--ghost btn--sm menutoggle" '
        'aria-expanded="false" aria-controls="topbar-menu">Menu</button>'
    )

    def test_signed_in_the_bar_has_a_menu_button_for_its_links_and_account(self):
        bar = topbar(self.client.get(reverse("data_quality:home")).content.decode())
        self.assertIn(self.BUTTON, bar)
        menu = bar.index('<div class="topbar__menu" id="topbar-menu">')
        # Brand, then the button, then what it opens: the links and Log out.
        self.assertLess(bar.index('class="brand"'), bar.index(self.BUTTON))
        self.assertLess(bar.index(self.BUTTON), menu)
        self.assertLess(menu, bar.index('<nav class="mainnav"'))
        self.assertLess(bar.index("</nav>"), bar.index("Log out"))

    def test_signed_out_there_is_nothing_to_fold_away(self):
        self.client.logout()
        html = self.client.get(reverse("data_quality:home")).content.decode()
        self.assertNotIn("menutoggle", topbar(html))
        self.assertIn("Sign up", topbar(html))

    def test_the_script_opens_and_closes_the_menu(self):
        html = self.client.get(reverse("data_quality:home")).content.decode()
        script = html[html.index("</header>"):html.index("<main")]
        self.assertIn("<script>", script)
        for part in ('querySelector(".menutoggle")', "aria-expanded", "has-menutoggle",
                     "is-open", '"Escape"', "button.focus()"):
            with self.subTest(part=part):
                self.assertIn(part, script)


class NavigationStyleTests(StylesheetMixin, TestCase):
    def media_blocks(self):
        """(condition, body) for every @media block; bodies hold no nested braces deeper than rules."""
        return re.findall(r"@media\s*\(([^)]*)\)\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}", self.css)

    def test_faint_text_is_readable_on_every_ground_it_sits_on(self):
        faint = self.tokens["ink-faint"]
        for ground in (self.tokens["surface"], self.tokens["canvas"], "#fafbfc"):
            with self.subTest(ground=ground):
                self.assertGreaterEqual(contrast_ratio(faint, ground), 4.5)

    def test_faint_text_still_reads_as_quieter_than_soft_text(self):
        self.assertLess(
            contrast_ratio(self.tokens["ink-faint"], self.tokens["surface"]),
            contrast_ratio(self.tokens["ink-soft"], self.tokens["surface"]),
        )

    def test_the_upload_item_is_readable_on_the_dark_bar(self):
        for selector in (".mainnav__planned", ".mainnav__tag"):
            with self.subTest(selector=selector):
                colour = self.declared_colour(selector, "color")
                self.assertGreaterEqual(contrast_ratio(colour, self.tokens["bar"]), 4.5)

    def test_the_upload_item_lines_up_with_the_links(self):
        self.assertRegex(self.css, r"(?m)^\.mainnav a,\s*\.mainnav__planned\s*\{[^}]*padding:\s*0\.25rem 0;"
                                   r"[^}]*border-bottom:\s*2px solid transparent")

    def test_every_keyboard_focus_gets_a_ring(self):
        ring = self.rule(":focus-visible")
        self.assertRegex(ring, r"outline:\s*2px solid var\(--accent\)")
        self.assertRegex(ring, r"outline-offset:\s*2px")

    def test_the_ring_is_visible_on_the_dark_bar(self):
        colour = re.search(r"outline-color:\s*([^;]+)", self.rule(".topbar :focus-visible"))
        self.assertIsNotNone(colour)
        self.assertGreaterEqual(contrast_ratio(self.colour(colour.group(1)), self.tokens["bar"]), 3)

    def test_form_fields_have_a_visible_edge(self):
        # WCAG 1.4.11: a field's border is how you see it is there (3:1).
        for ground in ("surface", "canvas"):
            with self.subTest(ground=ground):
                self.assertGreaterEqual(contrast_ratio(self.tokens["line-strong"], self.tokens[ground]), 3)
        self.assertRegex(self.css, r"textarea\s*\{[^}]*border:\s*1px solid var\(--line-strong\)")

    def test_the_skip_link_shows_itself_when_focused(self):
        self.assertRegex(self.rule(".skiplink"), r"transform:\s*translateY\(-")
        self.assertRegex(self.rule(".skiplink:focus"), r"transform:\s*none")

    def test_the_menu_button_only_shows_when_the_script_has_set_it_up(self):
        self.assertRegex(self.rule(".menutoggle"), r"display:\s*none")
        folded = [body for cond, body in self.media_blocks()
                  if re.search(r"\.topbar\.has-menutoggle \.topbar__menu\s*\{\s*display:\s*none", body)]
        self.assertEqual(len(folded), 1, "no media query folds the menu away")
        self.assertRegex(folded[0], r"\.topbar\.has-menutoggle \.menutoggle\s*\{[^}]*display:\s*inline-block")
        self.assertRegex(folded[0], r"\.topbar\.is-open \.topbar__menu\s*\{[^}]*display:\s*block")

    def test_the_top_bar_wraps_instead_of_pushing_the_page_sideways(self):
        """
        Signed in, the bar's one row needs about 1120px. With the 1000px
        column and wrapping only below 1040px, Log out hung past the column
        and the page scrolled sideways between 1041 and 1179px. The bar now
        always wraps, and its row is wide enough for one line on a large
        screen.
        """
        inner = self.rule(".topbar__inner")
        self.assertRegex(inner, r"flex-wrap:\s*wrap")
        self.assertGreaterEqual(int(re.search(r"max-width:\s*(\d+)px", inner).group(1)), 1170)
        self.assertRegex(self.rule(".mainnav"), r"flex-wrap:\s*wrap")

    def test_the_top_bar_breakpoints_follow_the_text_size(self):
        # em breakpoints scale with the browser's text-size setting, px ones do not.
        conditions = [cond for cond, body in self.media_blocks() if ".topbar" in body]
        self.assertGreaterEqual(len(conditions), 2)
        for cond in conditions:
            with self.subTest(media=cond):
                self.assertRegex(cond, r"^max-width:\s*[\d.]+em$")
