# Troubleshooting

## A file will not upload

If a submission produces a run with an error outcome, the file could not be evaluated at all. The usual causes are a missing header row, a delimiter the parser did not expect, or a file that is empty apart from its header. Check that the column names in the file still match the names the contract refers to, because a renamed column makes every rule that mentions it impossible to evaluate. An error run is recorded rather than discarded, so the attempt stays in the history and you can see when the problem started.

## Every row fails one rule

When a single rule fails on close to every row, suspect the rule or the export before suspecting the data. The three common causes are a column that changed type upstream, so a numeric check now sees formatted text; a column that was renamed or reordered, so the rule is reading the wrong field; and a legitimate change in the business that the contract has not caught up with. Look at the sample values first. If they all look reasonable to a human, the contract is almost certainly the thing that needs updating.

## The run says error rather than failed

Failed and error mean different things and are worth separating carefully. Failed means the checks ran and the data did not meet them, which is a statement about the file. Error means the checks never ran, which is a statement about the pipeline. A run of errors in a row usually points at a change in how the file is produced rather than a change in its contents. Because an error produces no violations, there is nothing to resolve; the fix is to make the file readable and submit it again, which creates a new run.

## Explanations are unavailable

If violations display without an AI explanation, the model could not produce a usable reply. This happens when the local model is not installed in the environment, when the reply failed validation twice, or when the fallback service is unreachable or out of quota. The violation itself is unaffected: the rule, the row counts and the sample values are all still shown, and the resolution can still be recorded by hand. Nothing in the review workflow depends on the explanation being present, which is why the page degrades to showing less rather than showing an error.
