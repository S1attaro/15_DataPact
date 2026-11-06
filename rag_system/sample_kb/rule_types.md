# DataPact rule types

## Not null

A NOT_NULL rule says a column must have a value in every row. It takes no parameters. A blank cell counts as a failure. This rule fits columns such as a student ID, where a missing value makes the whole row useless to the team that receives the file.

When a NOT_NULL rule fails, DataPact records how many rows were blank. The usual causes are a broken export or a new optional field in the source system. The owner of the dataset should ask the source team whether the blanks are expected before changing the contract.

## Unique

A UNIQUE rule says no value may appear twice in a column. It takes no parameters. It is the rule to use for keys such as an order number. A failed UNIQUE rule usually means the file was exported twice or two batches were joined together.

Duplicates can also come from a legitimate change. If a student can now hold two enrollments in one term, the key is no longer the student ID alone. In that case the contract should change, and the change should be saved as a new contract version.

## Range

A RANGE rule says a number must fall between a minimum and a maximum. The parameters hold those two limits. A credit hours column might use a range of 0 to 24. Values outside the limits are counted as violations, and sample values are kept for the person who reviews the run.

## Allowed values

An ALLOWED_VALUES rule lists every value a column may hold. The parameters hold the list. A status column might allow ACTIVE, INACTIVE and AUDIT. A new code in the file fails the rule even if it is valid in the source system, so this rule is the one most often changed when a source team adds a status.
