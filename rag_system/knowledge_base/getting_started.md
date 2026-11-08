# Getting started with DataPact

## Registering a dataset

A dataset in DataPact represents a data feed that your team receives repeatedly in the same shape, such as a monthly enrollment export or a weekly sales extract. You register it once from the Manage Datasets page by giving it a name, naming the team that sends it, and writing a short description of what the feed contains. The name has to be unique for the owner, so two people can each track a feed called Monthly Export without colliding. Registering a dataset does not upload any data. It only creates the subject that contracts and validation runs will attach to later. Until a contract exists, uploads for that dataset cannot be checked against anything.

## Who owns a dataset

Every dataset has exactly one owner, and ownership records who is accountable for the feed rather than who may look at it. Any signed-in user can view a dataset, search its contracts and read its violations. The owner is the person the team contacts when a file stops arriving or starts failing. Because ownership carries that responsibility, DataPact refuses to delete a user account that still owns datasets. The account has to be reassigned first, which prevents a single deletion from silently orphaning a feed and all of its history. Deactivating an account is the normal path when somebody leaves a team.

## Your first upload

Once a dataset has an active contract you can submit a file for checking. DataPact reads the file, counts the data rows, and tests every rule in the active contract against the relevant column. The result is recorded as a validation run, which is permanent. Nothing about the upload modifies the contract, and a failing file is not rejected or deleted. The point of the system is to produce evidence about what arrived, not to block the pipeline. If the file cannot be read at all, the run is recorded with an error outcome so the attempt still appears in the history.

## Reading the dashboard

The home page summarises the whole workspace in three numbers: how many datasets are registered, how many validation runs have been recorded, and how many violations are still open. An open violation is one that nobody has judged yet, so that figure is the real backlog. From there the navigation takes you to the dataset registry, contract search, quality history and reports. Signed-out visitors see only the home page and the public run-outcome summary, because every other page requires an account. The dashboard is deliberately small; it answers whether anything needs attention, not what to do about it.
