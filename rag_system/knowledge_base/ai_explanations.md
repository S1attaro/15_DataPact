# AI explanations

## What the explanation feature does

DataPact can draft an explanation for a violation. Given one failed rule, it returns a plain sentence describing what appears to have happened, a proposed cause of either a data issue or an outdated contract, and a suggested next step. The feature exists because the judgement it supports is the slowest part of reviewing a failure: an analyst normally has to read the sample rows and reason about whether the business changed. The draft is a starting point, not a decision. The resolution field on a violation is only ever written by a person, and the suggestion cannot change it.

## How a suggestion is produced

The system does not send free text to a model. It assembles the prompt from fields DataPact already holds about the violation: the dataset name, the column, the rule and its parameters, how many rows failed out of how many, and a few sample values. Those are flattened into a short labelled block and wrapped in a fixed instruction with a small number of worked examples, which measurably improves both accuracy and speed compared with asking the question cold. The model's reply is required to be structured, and the application validates it before showing anything.

## Why a suggestion may be missing

A violation can appear with no explanation attached, and that is a designed outcome rather than a bug. The model's reply is checked before use: it must parse, carry exactly the expected fields, and give a cause from the two permitted values. If the reply fails any of those checks the system retries once against a fallback, and if that also fails the page shows the violation with no AI text and a short note. The same thing happens when the model is unavailable. A missing explanation is always preferable to a confident wrong one.

## Limits of the suggestion

The explanation is a draft produced by a small model, and it carries three known limits. It sees only the fields listed above, so it knows nothing about an email from the data provider or a change announced in a meeting. It cannot tell a new legitimate category from a systematic typo any better than the sample values allow, which is the same constraint a human reader faces. And because it is required to answer in a fixed structure, a well-formed reply is not evidence of a correct one. Treat it as a first opinion from a colleague who has only read the violation record.
