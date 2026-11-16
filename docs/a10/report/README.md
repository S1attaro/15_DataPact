# A10 report (PDF source)

`a10_report.html` is the source of `../A10_report.pdf` (1.5 pages, US Letter).
The two images are crops of the dashboard screenshots in `docs/a10/`.

Rebuild the PDF after changing the HTML or swapping in new screenshots:

```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --no-pdf-header-footer --print-to-pdf=../A10_report.pdf a10_report.html
```

Every number comes from `data/ai_logs.csv` (308 benchmark requests) via
`docs/a10/analytics_design.md` and `docs/poster/key_numbers.md`.
