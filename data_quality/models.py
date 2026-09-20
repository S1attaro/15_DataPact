"""
Data models for DataPact.

DataPact records what a recurring dataset is expected to contain (a
"data contract"), checks each newly uploaded file against a specific
version of those expectations, and keeps a permanent record of what
passed, what failed, and what a person decided each failure meant.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Dataset(models.Model):
    """
    A data feed that a team receives repeatedly in the same shape, such as a
    monthly enrollment export or a weekly sales extract.

    Exists to give expectations and validation history a stable subject. Every
    contract and every validation run in DataPact belongs, directly or
    indirectly, to a Dataset.

    The owner is PROTECTed: ownership records who is accountable for the feed,
    so removing an account must not silently orphan the datasets it owns. The
    account must be reassigned first.
    """

    name = models.CharField(max_length=120)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="datasets",
    )
    source_team = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "name"],
                name="uniq_dataset_owner_name",
            )
        ]

    def __str__(self):
        return self.name


class Contract(models.Model):
    """
    One version of the expectations for a dataset: the written agreement about
    what its files must contain.

    Exists so that historical validation runs stay interpretable after the
    expectations change. A dataset normally has one ACTIVE contract, with
    earlier versions retained as RETIRED history. A contract version is treated
    as immutable once a validation run has used it; a later change is recorded
    by creating a new version rather than editing an existing one. This is a
    documented product rule enforced by application logic, not by the model.

    Deleting the dataset removes its contracts (CASCADE), because expectations
    describing a dataset that no longer exists have no meaning.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        RETIRED = "RETIRED", "Retired"

    dataset = models.ForeignKey(
        Dataset,
        on_delete=models.CASCADE,
        related_name="contracts",
    )
    version_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    change_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Why this version exists, e.g. 'Added AUDIT to allowed status values'.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset__name", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "version_number"],
                name="uniq_contract_dataset_version",
            )
        ]

    def __str__(self):
        return f"{self.dataset.name} - v{self.version_number} ({self.status})"


class ValidationRule(models.Model):
    """
    A single checkable expectation about one column within one contract
    version, such as "credit_hours must be between 0 and 24".

    Exists so that expectations are stored as data rather than written into
    code, which is what allows a contract to be authored, versioned, and
    inspected without changing the application.

    Deleting the contract removes its rules (CASCADE), because a rule has no
    existence outside the contract version it belongs to.
    """

    class RuleType(models.TextChoices):
        NOT_NULL = "NOT_NULL", "Not null"
        TYPE_MATCH = "TYPE_MATCH", "Type match"
        RANGE = "RANGE", "Range"
        ALLOWED_VALUES = "ALLOWED_VALUES", "Allowed values"
        REGEX = "REGEX", "Format (regex)"
        UNIQUE = "UNIQUE", "Unique"

    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    column_name = models.CharField(max_length=100)
    rule_type = models.CharField(max_length=20, choices=RuleType.choices)
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text='Type-specific arguments, e.g. {"min": 0, "max": 24}. '
                  "Empty for NOT_NULL and UNIQUE.",
    )

    class Meta:
        ordering = ["column_name", "rule_type"]

    def __str__(self):
        return f"{self.column_name} - {self.get_rule_type_display()}"


class ValidationRun(models.Model):
    """
    One occasion on which an uploaded file was checked against one contract
    version.

    Exists as the permanent audit record of what was checked, when, by whom,
    and against which expectations.

    The contract is PROTECTed: deleting a contract version that has been used
    to validate a file would leave that run uninterpretable, since there would
    be no record of what the file was measured against. A used contract is
    retired, never deleted. The submitting user is SET_NULL because the record
    must outlive the account; losing who ran the check is acceptable, losing
    the check itself is not.
    """

    class Status(models.TextChoices):
        PASSED = "PASSED", "Passed"
        FAILED = "FAILED", "Failed"
        ERROR = "ERROR", "Error"

    contract = models.ForeignKey(
        Contract,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_runs",
    )
    file_name = models.CharField(max_length=255)
    row_count = models.PositiveIntegerField(
        help_text="Number of data rows in the uploaded file."
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.file_name} - {self.status} ({self.started_at:%Y-%m-%d})"


class Violation(models.Model):
    """
    One rule that failed during one validation run, together with the evidence
    needed to act on it and the human judgement about what the failure meant.

    Exists because a failed check is only useful if the analyst can see the
    actual rows and values responsible. A Violation is the aggregated result
    for one rule in one run, not one record per bad cell.

    The resolution field records DataPact's central distinction: a failure may
    mean the incoming data is wrong (DATA_ISSUE), or that the expectation has
    fallen out of date because the underlying reality legitimately changed
    (CONTRACT_UPDATED). The system does not decide this; a person does.

    The run is CASCADEd because a violation is a detail of one run. The rule is
    PROTECTed because a violation pointing at a deleted rule could not be
    explained.
    """

    class Resolution(models.TextChoices):
        OPEN = "OPEN", "Open"
        DATA_ISSUE = "DATA_ISSUE", "Data issue"
        CONTRACT_UPDATED = "CONTRACT_UPDATED", "Contract updated"

    run = models.ForeignKey(
        ValidationRun,
        on_delete=models.CASCADE,
        related_name="violations",
    )
    rule = models.ForeignKey(
        ValidationRule,
        on_delete=models.PROTECT,
        related_name="violations",
    )
    failed_row_count = models.PositiveIntegerField()
    sample_values = models.JSONField(
        default=list,
        blank=True,
        help_text='Examples of offending data, e.g. [{"row": 118, "value": "AUDIT"}].',
    )
    message = models.CharField(max_length=255)
    resolution = models.CharField(
        max_length=20,
        choices=Resolution.choices,
        default=Resolution.OPEN,
    )

    class Meta:
        ordering = ["-failed_row_count"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "rule"],
                name="uniq_violation_run_rule",
            )
        ]

    def __str__(self):
        return f"{self.rule.column_name} - {self.rule.get_rule_type_display()} ({self.failed_row_count} rows)"
