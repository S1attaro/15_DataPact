"""
Template tags for the application shell (product redesign, Stage 3B.1).

handbook_status lets base.html label the Handbook link with whether this
server can answer handbook questions. It asks the same function the Handbook
page asks (ai.retrieval.handbook_status), so the navigation and the page can
never disagree, in development or on production. That function reads only
settings and a folder listing; it never loads a model. ai.retrieval is
already imported on every request (urls.py imports handbook_views, which
imports it), so this adds no import cost.
"""

from django import template

from data_quality.ai import retrieval

register = template.Library()


@register.simple_tag
def handbook_status():
    """None when the handbook can answer here, otherwise why not ("off", "not_configured", "missing_kb")."""
    return retrieval.handbook_status()
