# A10 report (PDF source)

`a10_report.html` is the source of `../A10_report.pdf` (1.5 pages, US Letter).

The two images are crops of the `/analytics/` page rendered locally from this
code over `data/ai_logs.csv`, with the data source set to "Benchmark run" (not
production screenshots; those are attached to the submission separately):

- `kpis.png`: the summary cards of all three sections.
- `dashboard_panels.png`: the latency histogram (P1), out-of-scope outcomes
  (B3) and cost per 1,000 requests by model (C1).

Rebuild the PDF after changing the HTML or swapping in new screenshots:

```
# macOS
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer --print-to-pdf=../A10_report.pdf a10_report.html
# Windows (Git Bash)
"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --no-pdf-header-footer --print-to-pdf=../A10_report.pdf a10_report.html
```

Every number comes from `data/ai_logs.csv` (308 benchmark requests) via
`docs/a10/analytics_design.md` and `docs/poster/key_numbers.md`. Latency
figures use the 288 requests that reached a model; outcomes and cost use all 308.
