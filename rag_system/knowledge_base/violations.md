# Violations

## What a violation records

A violation is the result of one rule failing during one run. It is an aggregate, not one record per bad cell: a file with fifty thousand bad rows produces a single violation that reports fifty thousand failed rows, rather than fifty thousand separate entries. Each violation stores the rule that failed, the number of rows affected, a short message, a few sample values and the resolution a person recorded. There can only ever be one violation for a given rule within a given run, which stops a partially re-run validation from writing a second entry and inflating the failure counts.

## Sample values

Every violation carries a small number of example values that broke the rule, along with the row numbers they came from. Samples exist because a failure count on its own is rarely actionable: knowing that twelve rows failed a format rule tells you far less than seeing that the twelve values all have a trailing space. Samples are deliberately limited to a handful rather than the full set, which keeps the record small and readable. They are taken from the uploaded file, so they may contain real values from the source system and should be treated with the same care as the file itself.

## Deciding the resolution

A violation starts life as open, meaning nobody has judged it yet. A person then records what the failure meant. DataPact never decides this automatically, because the decision is about the business rather than about the data. The two outcomes are that the incoming data was wrong, or that the data was fine and the rule had fallen out of date. Recording the decision matters beyond the current file: the same violation often returns in a later upload, and the team can then see how it was handled last time instead of relitigating it.

## Data issue or contract updated

Telling the two resolutions apart is the central judgement in DataPact. A data issue means the file is wrong and somebody upstream should fix it. A contract update means reality changed and the rule should be rewritten. Three signals usually separate them. How many rows failed: a handful suggests data entry, a large and consistent block suggests a change in the business. Whether the offending values are all the same: one repeated new value suggests a new legitimate category, while scattered variants suggest typos. And whether the value looks plausible: a negative quantity is never legitimate, while a new campus code probably is.

## Recurring violations

When the same rule fails in run after run, the violation is recurring, and that pattern is itself information. A recurring failure resolved as a data issue every month means the upstream fix never happened, and the conversation should move from the file to the process that produces it. A recurring failure that keeps being resolved as a contract update means the rule is being patched repeatedly instead of rewritten properly. The quality history page is the fastest way to see this, because it shows outcomes over time rather than one run at a time.
