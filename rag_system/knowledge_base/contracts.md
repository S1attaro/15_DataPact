# Data contracts

## What a contract is

A contract is the written agreement about what the files of a dataset must contain. It belongs to exactly one dataset and holds a list of rules, each describing one checkable expectation about one column. A contract is the thing that makes a validation result meaningful: without it, a file is just data, and there is no standard to measure it against. Contracts are written by people who understand the feed, usually the analyst who receives it, and they are meant to be readable by somebody who is not an engineer. A dataset normally has one contract that is currently in force, with earlier ones kept as history.

## Contract versions

Each contract carries a version number that counts from one within its dataset, so two datasets can both have a version three without ambiguity. Versions exist so that historical validation runs stay interpretable after expectations change. A run records which contract version it was judged against, which means you can look at a result from six months ago and know exactly which rules produced it. Version numbers are unique per dataset and are enforced by the database, so two rows cannot both claim to be version three of the same contract. Changing expectations means adding a version, never renumbering an existing one.

## Activating and retiring a version

A contract version has one of three statuses. A draft is being written and is not used to check anything. An active version is the one that incoming files are measured against, and a dataset normally has exactly one. A retired version is kept for history after a newer version replaced it. Moving a version from draft to active is what puts it into force, and the previously active version becomes retired at the same moment. Retired versions are never deleted, because deleting one would leave every validation run that used it impossible to interpret.

## Writing a new rule

A rule names one column, chooses a rule type, and supplies whatever parameters that type needs. A range rule needs a minimum and a maximum; an allowed-values rule needs the list of permitted values; a not-null rule needs no parameters at all. Rules are stored as data rather than written into code, which is what lets an analyst author and inspect them without a developer changing the application. Each rule belongs to exactly one contract version, so adding a rule to a version that is already in use is not possible. The change goes into a new version instead.

## Editing a contract that has been used

A contract version that has been referenced by a validation run must never be edited. Changing its rules afterwards would alter the meaning of a result that already happened, so a run recorded as passing could later appear to have been judged by rules it never saw. Any change is therefore saved as a new version, and the old one is retired rather than modified. The database enforces part of this by refusing to delete a contract that has runs attached to it. A version that has never been used has no runs and can be deleted cleanly, which is the intended behaviour for an abandoned draft.
