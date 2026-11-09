# Validation runs

## Starting a run

A validation run is one occasion on which an uploaded file was checked against one contract version. You start a run by submitting a file for a dataset that has an active contract. DataPact records the file name, the number of data rows it contained, who submitted it, when it started and when it finished. The run always points at the contract version rather than at the dataset, so the rules that produced the result are never ambiguous. There is no way to run a file against a draft or a retired version, which keeps results comparable with each other over time.

## How a run is scored

Every rule in the active contract is evaluated against the file, and each rule produces either a pass or one aggregated violation. A run passes only when every rule passes. It fails when at least one rule fails, regardless of how many rows were involved, because a single broken rule still means the file did not meet the agreement. The run does not stop at the first failure; all rules are evaluated so that one upload tells you everything that is wrong rather than only the first problem. That matters when several columns changed at once.

## Run outcomes

A run finishes in one of three states. Passed means every rule passed. Failed means at least one rule produced a violation, and the violations are attached to the run for review. Error means the file could not be evaluated at all, usually because it was unreadable, had no header row, or was missing columns the contract refers to. Error is deliberately distinct from failed: a failed run tells you something true about the data, while an error tells you the check never happened. Treating them the same would make the quality history misleading.

## Row counts and partial files

Each run records the total number of data rows in the file, and each violation records how many of those rows broke its rule. The ratio between the two is often more informative than either number alone. A rule that fails on three rows out of five thousand is probably a data-entry problem worth fixing at the source. The same rule failing on four thousand rows out of five thousand usually means the contract is out of date or the file is a different export than expected. A sharp change in the total row count between runs is itself worth investigating even when every rule passes.
