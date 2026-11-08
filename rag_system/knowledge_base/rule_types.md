# Rule types

## Not null

A not-null rule asserts that a column always carries a value. It fails on empty strings and on missing fields as well as on true nulls, because all three mean the same thing to somebody reading a report. This rule needs no parameters. It is the cheapest check to write and usually the first one worth adding to a new contract, since a column that is sometimes blank will break almost any downstream calculation. When it fails on a large share of rows, the usual cause is an upstream export that changed which columns it includes rather than a genuine data-entry problem, so check the file header before chasing individual records.

## Type match

A type-match rule asserts that every value in a column can be read as the declared type, such as an integer, a decimal or a date. It fails when a value cannot be parsed, which most often happens because a numeric column arrives with thousands separators, currency symbols or a placeholder like N/A. Type failures tend to cluster: if one row fails, many do, because the cause is a formatting decision made by the exporting system rather than a mistake in a single record. Fixing the export is almost always better than loosening the rule, because a column that is sometimes text and sometimes a number is hard to use.

## Range

A range rule asserts that numeric values fall between a minimum and a maximum. It takes two parameters and fails on any value outside them. Ranges catch two very different problems. The first is impossible data, such as a negative quantity or a credit-hours value of ninety-nine, which usually means a parsing error or a sentinel value like minus nine thousand nine hundred and ninety-nine standing in for missing. The second is a legitimate change in the business, such as a course that now allows more hours than the rule was written for. The sample values usually make it obvious which of the two you are looking at.

## Allowed values

An allowed-values rule asserts that a column only contains entries from a fixed list, such as a set of status codes or campus names. It fails on anything outside the list. This rule type produces the clearest signal of an outdated contract: when a single new value appears consistently across many rows, the business has almost certainly added a category and the list needs extending. When a handful of rows carry misspellings or stray whitespace of existing values, that is a data problem instead. Reading how many distinct new values appear, and how often, separates the two cases faster than reading the rows.

## Format

A format rule asserts that values match a regular expression, which is how DataPact checks identifiers with a fixed shape such as an eight-digit student number or a term code made of four digits and a letter. It fails on anything the pattern does not match. Format failures are usually genuine data problems, because identifiers rarely change shape without an announcement. Common causes are leading or trailing whitespace, an identifier that arrived with a prefix attached, or a value that was truncated somewhere in the pipeline. Because the pattern is strict, it is worth confirming the pattern itself is right before reporting a failure upstream.

## Unique

A unique rule asserts that no value appears twice in a column, which is how key columns are protected. It fails when duplicates exist and reports how many rows were involved. Duplicates usually mean one of two things. Either the file was exported twice and concatenated, in which case entire blocks of rows repeat and the row count is roughly double what it should be, or a join upstream multiplied records, in which case only some identifiers repeat and the rest of the row differs. Comparing the number of failed rows against the total row count is the quickest way to tell which happened.
