"""
A10 analytics: logging AI requests and the dashboard at /analytics/.

recorder.py   writes one AIRequestLog row per AI request (Connor)
pricing.py    turns tokens and time into dollars (Connor)
charts.py     small Vega-Lite helpers every section can use (Connor)
cost.py       cost section (Connor)
performance.py  performance section (Ashok)
behavior.py     user behavior section (Ashok)

Each section module has one function, <name>_context(qs), that takes the
filtered AIRequestLog queryset and returns a dict for its template partial in
templates/data_quality/analytics/.
"""
