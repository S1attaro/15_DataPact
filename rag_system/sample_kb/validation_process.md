# Validation process

## Contracts and versions

A contract is the written agreement about what the files of a dataset must contain. Each contract belongs to one dataset and holds a list of rules. A contract that has been used in a validation run must never be edited. Any change is saved as a new version, so old runs can still be read against the rules they were checked with.

## Validation runs

A validation run is one occasion on which an uploaded file was checked against one contract version. The run records the file, the contract version and the outcome. A run passes when every rule passes. A run fails when at least one rule fails, and each failed rule produces one aggregated violation rather than one record per bad row.

## Reviewing violations

A violation stores the rule that failed, the number of failed rows and a few sample values. A person then records what the failure meant. The resolution says whether the data was wrong or the contract was out of date. Keeping this decision matters because the same violation may come back in a later file, and the team can see how it was handled last time.
