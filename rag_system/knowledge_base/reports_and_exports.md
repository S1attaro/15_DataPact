# Reports and exports

## The reports page

The reports page summarises validation activity across every dataset rather than one at a time. It opens with a totals line giving the number of datasets, the number of validation runs recorded and how many of those runs failed. Below that are grouped summaries that count runs by outcome and by dataset, so you can see at a glance whether failures are spread across the whole workspace or concentrated in one feed. The page is read-only and requires an account. It is the usual starting point for a weekly review, because it answers which feed deserves attention before you open any individual run.

## Grouped summaries

Two groupings are provided. Runs by outcome counts how many runs passed, failed or errored, which gives the overall health of the pipeline in three numbers. Runs by dataset counts how many runs each feed has produced, which shows where the volume is. Reading them together is more useful than either alone: a workspace with many failures concentrated in a single dataset has a different problem from one with failures spread evenly, and the fix is different too. Both summaries are computed from the database at the moment the page loads, so they always reflect current data.

## CSV export

The reports page offers a download of validation run data as CSV. The file opens directly in a spreadsheet, uses the first row as column headers, and contains one row per validation run ordered consistently. The download filename carries a timestamp, so repeated exports do not overwrite each other and it is always clear when a given extract was taken. CSV is the right choice when somebody wants to pivot the data, chart it, or hand it to a colleague who does not use DataPact. It contains no nested structure, which is the tradeoff for being universally readable.

## JSON export

The same data is also available as JSON, which suits anything that will be read by a program rather than a person. The JSON export is pretty-printed and wraps the records in a small envelope carrying the time the export was generated and how many records it contains. That metadata matters when the file is archived, because a bare list of records gives no way to tell when it was produced or whether it is complete. Like the CSV, the filename is timestamped. Both exports require an account, since they contain dataset names and owner information.
